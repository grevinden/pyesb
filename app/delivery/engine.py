"""Delivery engine — одна попытка HTTP POST с retry, DLQ, middleware."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from aiorun import shutdown_waits_for
from apscheduler import current_async_scheduler, current_job
from cashews import CircuitBreakerOpen

from app.config import settings
from app.events import (
    CircuitBreakerOpenEvent,
    DeliveryAttemptEvent,
    DeliveryFailedEvent,
    DeliveryHttpErrorEvent,
    DeliveryResponseEvent,
    DeliverySuccessEvent,
    LogEvent,
    ScheduleRef,
)
from app.orchestration.dlq import (
    _attempt_counts,
    _check_permanent_failure,
    _cleanup_schedule_tracking,
)

from .client import _get_http_client, _http_post_with_cb
from .context import message_id_var, trace_id_var
from .semaphore import _delivery_semaphore, _in_flight, is_shutting_down

__all__ = [
    "deliver_payload",
]

# Log body limits
_MAX_BODY_CHARS: int = settings.LOG_BODY_MAX_CHARS
_MAX_RESPONSE_BODY_CHARS: int = settings.LOG_RESPONSE_BODY_MAX_CHARS


async def deliver_payload(
    url: str,
    body: dict | list | None,
    headers: list[tuple[str, str]] | None,
    timeout: int,
    destination: str,
    message_id: str,
    trace_id: str | None = None,
) -> None:
    """Выполняет одну попытку POST-доставки.

    При успехе (2xx) — удаляет расписание (``delivery_success``).
    При ошибке — возвращает управление; APScheduler повторит
    по ``IntervalTrigger`` пока не истечёт TTL.
    """
    # ── Shutdown guard ────────────────────────────────────────────────
    if is_shutting_down():
        LogEvent().emit(
            event="delivery_skipped_shutdown",
            message_id=message_id,
            trace_id=trace_id,
            destination=destination,
            url=url,
        )
        return

    message_id_var.set(message_id)
    trace_id_var.set(trace_id)

    job = current_job.get()
    schedule_id: str = job.schedule_id if job.schedule_id is not None else "unknown"

    headers_dict = dict(headers) if headers else {}
    body_repr = await asyncio.to_thread(_truncate_json, body, _MAX_BODY_CHARS)

    current_task = asyncio.current_task()
    assert current_task is not None, "deliver_payload must run inside an asyncio task"
    _in_flight.add(current_task)

    _attempt_counts[schedule_id] = _attempt_counts.get(schedule_id, 0) + 1

    try:
        body_size = await asyncio.to_thread(_json_size, body)
        DeliveryAttemptEvent(
            schedule_id=schedule_id,
            destination=destination,
            url=url,
            headers=headers,
            body_size=body_size,
            body=body_repr,
            timeout=timeout,
        ).emit()

        semaphore_acquired: bool = False
        if not is_shutting_down():
            await _delivery_semaphore.acquire()
            semaphore_acquired = True

        t0 = datetime.now(timezone.utc)

        async def _http_post() -> httpx.Response:
            client = _get_http_client()
            return await _http_post_with_cb(
                client,
                url,
                headers_dict,
                body,
                timeout,
            )

        try:
            resp = await shutdown_waits_for(_http_post())

            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            resp_body = _truncate_text(resp.text, _MAX_RESPONSE_BODY_CHARS)

            DeliveryResponseEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                status_code=resp.status_code,
                response_headers=dict(resp.headers),
                response_body=resp_body,
                duration_ms=duration_ms,
            ).emit()

            resp.raise_for_status()

        except httpx.HTTPStatusError as exc:
            DeliveryHttpErrorEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                status_code=exc.response.status_code,
                error=_short_exc(exc),
            ).emit()
            _check_permanent_failure(
                schedule_id,
                message_id,
                destination,
                url,
                trace_id,
            )
            return

        except CircuitBreakerOpen as exc:
            CircuitBreakerOpenEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                error=_short_exc(exc),
            ).emit()
            return

        except Exception as exc:
            duration_ms = _elapsed_ms(t0)
            DeliveryFailedEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                error=_short_exc(exc),
                duration_ms=duration_ms,
            ).emit()
            _check_permanent_failure(
                schedule_id,
                message_id,
                destination,
                url,
                trace_id,
            )
            return

        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        DeliverySuccessEvent(
            schedule_id=schedule_id,
            destination=destination,
            url=url,
            status_code=resp.status_code,
            duration_ms=duration_ms,
        ).emit()

        sched = current_async_scheduler.get()
        if sched is not None:
            try:
                await sched.remove_schedule(schedule_id)
            except (LookupError, Exception):
                ScheduleRef(schedule_id=schedule_id).emit(event="schedule_remove_skipped")

        _cleanup_schedule_tracking(schedule_id)

    finally:
        _in_flight.discard(current_task)
        if semaphore_acquired:
            _delivery_semaphore.release()


# ── Helpers ──────────────────────────────────────────────────────────


def _short_exc(exc: Exception) -> str:
    """Format exception as ``TypeName: message``."""
    return f"{type(exc).__name__}: {exc}"


def _elapsed_ms(t0: datetime) -> int | None:
    """Calculate elapsed milliseconds since t0."""
    try:
        return int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    except Exception:
        return None


def _truncate_text(text: str | None, limit: int) -> str | None:
    """Truncate text to limit chars, appending ``...`` if needed."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _truncate_json(obj: object, limit: int) -> str | None:
    """JSON-serialize and truncate."""
    import json as json_mod

    try:
        raw = json_mod.dumps(obj, default=str)
    except Exception:
        raw = str(obj)
    return _truncate_text(raw, limit)


def _json_size(obj: object) -> int | None:
    """Return JSON byte size of object."""
    import json as json_mod

    try:
        return len(json_mod.dumps(obj, default=str).encode("utf-8"))
    except Exception:
        return None
