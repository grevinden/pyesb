"""Delivery engine — POST to webhook URLs with retry via APScheduler.

На каждый вызов создаётся Schedule с ``IntervalTrigger``.
TTL задаёт конечное время — APScheduler сам повторяет попытки до TTL.
Все события пишутся в JSONL через structlog — БД не пухнет.
Счётчик попыток не нужен — TTL единственный лимит.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from aiorun import shutdown_waits_for
from apscheduler import CoalescePolicy, current_async_scheduler, current_job
from apscheduler.triggers.interval import IntervalTrigger

from .context import message_id_var, trace_id_var
from .events import (
    DeliveryAttemptEvent,
    DeliveryFailedEvent,
    DeliveryHttpErrorEvent,
    DeliveryResponseEvent,
    DeliveryScheduledEvent,
    DeliverySkippedShutdownEvent,
    DeliverySuccessEvent,
    ScheduleRemoveSkippedEvent,
    ShutdownCancelledEvent,
    ShutdownDeliveriesCompletedEvent,
    ShutdownTimeoutEvent,
    ShutdownWaitingEvent,
    fmt_headers,
)

# ── Shutdown guard ───────────────────────────────────────────────────
# Множество asyncio.Task-ов, которые сейчас выполняют HTTP-запрос.
# Используется в lifespan для ожидания завершения доставок.
_in_flight: set[asyncio.Task] = set()

# Флаг: приложение выключается. Новые вызовы deliver_payload
# не выполняют HTTP-запрос, а сразу возвращаются (no-op).
_shutting_down: bool = False


_MAX_BODY_CHARS: int = 4096
_MAX_RESPONSE_BODY_CHARS: int = 4096

# ---------------------------------------------------------------------------
# APScheduler-совместимая функция доставки (один вызов = одна попытка)
# ---------------------------------------------------------------------------


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

    Во время shutdown (``_shutting_down = True``) новые вызовы
    сразу возвращаются — HTTP-запрос не выполняется.
    """
    # ── Shutdown guard ────────────────────────────────────────────────
    if _shutting_down:
        DeliverySkippedShutdownEvent(
            message_id=message_id,
            trace_id=trace_id,
            destination=destination,
            url=url,
        ).emit()
        return

    # Фиксируем message_id и trace_id в contextvars — structlog
    # автоматически inject их во все последующие логи.
    message_id_var.set(message_id)
    trace_id_var.set(trace_id)

    job = current_job.get()
    schedule_id: str = job.schedule_id if job.schedule_id is not None else "unknown"

    headers_dict = dict(headers) if headers else {}
    body_repr = _truncate_json(body, _MAX_BODY_CHARS)

    # Регистрируемся как in-flight — shutdown будет ждать нас
    current_task = asyncio.current_task()
    assert current_task is not None, "deliver_payload must run inside an asyncio task"
    _in_flight.add(current_task)
    try:
        # ── delivery_attempt ──────────────────────────────────────────
        DeliveryAttemptEvent(
            schedule_id=schedule_id,
            destination=destination,
            url=url,
            headers=fmt_headers(headers),
            body_size=_json_size(body),
            body=body_repr,
            timeout=timeout,
        ).emit()

        # ── HTTP POST (защищённый от отмены) ──────────────────────────
        t0 = datetime.now(timezone.utc)
        timeout_cfg = httpx.Timeout(timeout)

        async def _http_post() -> httpx.Response:
            """Собственно HTTP-вызов. ``shutdown_waits_for`` гарантирует,
            что этот таск не будет отменён даже при CancelledError
            в нашем APScheduler-контейнере."""
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                return await client.post(url, json=body, headers=headers_dict)

        try:
            # shutdown_waits_for создаёт независимый таск,
            # который не отменяется при остановке APScheduler
            resp = await shutdown_waits_for(_http_post())

            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            resp_body = _truncate_text(resp.text, _MAX_RESPONSE_BODY_CHARS)

            # ── delivery_response (ДО raise_for_status) ───────────────
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
            return  # APScheduler повторит по IntervalTrigger

        except Exception as exc:
            duration_ms = _elapsed_ms(t0)
            DeliveryFailedEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                error=_short_exc(exc),
                duration_ms=duration_ms,
            ).emit()
            return  # APScheduler повторит по IntervalTrigger

        # ── delivery_success ──────────────────────────────────────────
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        DeliverySuccessEvent(
            schedule_id=schedule_id,
            destination=destination,
            url=url,
            status_code=resp.status_code,
            duration_ms=duration_ms,
        ).emit()

        # Убираем расписание — доставлено
        sched = current_async_scheduler.get()
        if sched is not None:
            try:
                await sched.remove_schedule(schedule_id)
            except (LookupError, Exception):
                ScheduleRemoveSkippedEvent(schedule_id=schedule_id).emit()

    finally:
        _in_flight.discard(current_task)


# ---------------------------------------------------------------------------
# Ожидание завершения in-flight доставок (вызывается из shutdown)
# ---------------------------------------------------------------------------


async def wait_for_in_flight(timeout: float = 30) -> None:
    """Дождаться завершения всех in-flight доставок.

    Вызывается из shutdown-последовательности **до** того как
    APScheduler остановит свои task group-и.
    """
    if not _in_flight:
        return
    ShutdownWaitingEvent(count=len(_in_flight), timeout=timeout).emit()
    done, pending = await asyncio.wait(_in_flight.copy(), timeout=timeout)
    if pending:
        ShutdownTimeoutEvent(remaining=len(pending), timeout=timeout).emit()
        # Force cancel
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        ShutdownCancelledEvent(count=len(pending)).emit()
    else:
        ShutdownDeliveriesCompletedEvent().emit()


# ---------------------------------------------------------------------------
# Создание расписания
# ---------------------------------------------------------------------------


async def create_delivery_schedule(
    scheduler: object,
    *,
    destination: str,
    url: str,
    body: dict | list | None,
    headers: list[tuple[str, str]] | None,
    timeout: int,
    pause: int,
    ttl: int,
    trace_id: str | None = None,
    message_id: str,
) -> str:
    """Создать APScheduler Schedule для доставки payload'а.

    Первый fire time — ``now`` (немедленно).
    Последний — ``now + ttl`` секунд.
    Между ними — ``pause`` секунд.

    После истечения TTL расписание завершается автоматически.
    """
    schedule_id = f"delivery_{destination}_{uuid4().hex}"

    now = datetime.now(timezone.utc)
    end = now + timedelta(seconds=ttl)

    await scheduler.add_schedule(  # type: ignore[union-attr]
        deliver_payload,
        IntervalTrigger(
            seconds=max(1, pause),
            start_time=now,
            end_time=end,
        ),
        id=schedule_id,
        args=[url, body, headers, timeout, destination, message_id, trace_id],
        misfire_grace_time=None,
        coalesce=CoalescePolicy.latest,
    )

    DeliveryScheduledEvent(
        message_id=message_id,
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        pause=pause,
        ttl=ttl,
        trace_id=trace_id,
        end_time=end.isoformat(),
    ).emit()

    return schedule_id


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _short_exc(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _elapsed_ms(t0: datetime) -> int | None:
    try:
        return int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    except Exception:
        return None


def _truncate_text(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _truncate_json(obj: object, limit: int) -> str | None:
    import json as json_mod

    try:
        raw = json_mod.dumps(obj, default=str)
    except Exception:
        raw = str(obj)
    return _truncate_text(raw, limit)


def _json_size(obj: object) -> int | None:
    import json as json_mod

    try:
        return len(json_mod.dumps(obj, default=str).encode("utf-8"))
    except Exception:
        return None
