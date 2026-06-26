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
from cashews import CircuitBreakerOpen, cache

from .config import settings
from .context import message_id_var, trace_id_var
from .events import (
    CircuitBreakerOpenEvent,
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

# ── Concurrency control ───────────────────────────────────────────────
# Семафор ограничивает количество одновременно выполняемых HTTP-запросов.
# Предотвращает исчерпание соединений (DB, внешние API, сокеты)
# при всплеске нагрузки.
_delivery_semaphore: asyncio.Semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DELIVERIES)
"""Maximum concurrent HTTP deliveries (across all destinations).

Выбирается исходя из:
* лимитов целевых серверов (concurrent connections per host),
* доступных файловых дескрипторов (ulimit -n),
* размера пула соединений ``httpx``.
"""

# ── Circuit breaker (cashews) ───────────────────────────────────────────
# In-memory circuit breaker для защиты целевых серверов от повторяющихся
# ошибок. Circuit breaker per URL: если за минуту >10 ошибок на URL,
# доставка на этот URL приостанавливается на 5 минут.
# Не требует Redis — in-memory достаточно для защиты от лавины.
cache.setup("mem://")

# ── Shared httpx client ──────────────────────────────────────────────
# Один AsyncClient на все HTTP-доставки — пул соединений,
# не создаём клиент на каждый запрос (C2 performance fix).
_http_client: httpx.AsyncClient | None = None
"""Lazily initialized shared HTTP client. Close via ``close_http_client()``."""


@cache.circuit_breaker(
    errors_rate=10,
    period="1m",
    ttl="5m",
    half_open_ttl="1m",
    key="{url}",
)
async def _http_post_with_cb(
    client: httpx.AsyncClient,
    url: str,
    headers_dict: dict[str, str],
    body: dict | list | None,
    timeout: int,
) -> httpx.Response:
    """HTTP POST с circuit breaker per URL.

    Если за последнюю минуту на этот URL было >=10 ошибок,
    circuit breaker размыкается на 5 минут ("open").
    Все последующие вызовы на этот URL сразу бросают
    ``CircuitBreakerOpen`` — без реального HTTP-запроса.

    Через 1 минуту half-open — один запрос пропускается.
    Если успешен — circuit breaker закрывается ("closed"),
    если нет — снова открывается на 5 минут.

    Это защищает целевой сервер от лавины запросов,
    когда он уже падает или перегружен.
    """
    return await client.post(url, json=body, headers=headers_dict, timeout=timeout)


def _get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, creating it if needed.

    Client is configured with connection pool limits from settings.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=settings.MAX_CONCURRENT_DELIVERIES,
                max_keepalive_connections=settings.MAX_CONCURRENT_DELIVERIES,
            ),
            verify=False,  # Требование заказчика: отключить проверку SSL-сертификата
        )
    return _http_client


async def close_http_client() -> None:
    """Close the shared httpx.AsyncClient.

    Call during shutdown (lifespan) to release connection pool resources.
    """
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ── Shutdown guard ───────────────────────────────────────────────────
# Множество asyncio.Task-ов, которые сейчас выполняют HTTP-запрос.
# Используется в lifespan для ожидания завершения доставок.
_in_flight: set[asyncio.Task] = set()

# Флаг: приложение выключается. Новые вызовы deliver_payload
# не выполняют HTTP-запрос, а сразу возвращаются (no-op).
_shutting_down: bool = False

# ── DLQ tracking ────────────────────────────────────────────────────────
# Храним end_time для каждого schedule_id.
# Когда retry исчерпаны, а HTTP всё ещё не 2xx — ``DeliveryExpiredEvent``.
_schedule_end_times: dict[str, datetime] = {}

# Счётчик попыток на schedule (сбрасывается при перезапуске).
_attempt_counts: dict[str, int] = {}


# Log body limits (configurable via FWQ_LOG_BODY_MAX_CHARS / FWQ_LOG_RESPONSE_BODY_MAX_CHARS)
_MAX_BODY_CHARS: int = settings.LOG_BODY_MAX_CHARS
_MAX_RESPONSE_BODY_CHARS: int = settings.LOG_RESPONSE_BODY_MAX_CHARS

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
    # json.dumps в _truncate_json / _json_size — тяжёлые операции,
    # выносим в asyncio.to_thread (H1 fix).
    body_repr = await asyncio.to_thread(_truncate_json, body, _MAX_BODY_CHARS)

    # Регистрируемся как in-flight — shutdown будет ждать нас
    current_task = asyncio.current_task()
    assert current_task is not None, "deliver_payload must run inside an asyncio task"
    _in_flight.add(current_task)

    # Увеличиваем счётчик попыток для DLQ
    _attempt_counts[schedule_id] = _attempt_counts.get(schedule_id, 0) + 1

    try:
        # ── delivery_attempt ──────────────────────────────────────────
        body_size = await asyncio.to_thread(_json_size, body)
        DeliveryAttemptEvent(
            schedule_id=schedule_id,
            destination=destination,
            url=url,
            headers=fmt_headers(headers),
            body_size=body_size,
            body=body_repr,
            timeout=timeout,
        ).emit()

        # ── Concurrency guard (Semaphore) ──────────────────────────────
        # Ограничиваем количество одновременно выполняемых HTTP-запросов.
        # Если все ``_delivery_semaphore`` заняты — ожидаем освобождения.
        # Это предотвращает исчерпание соединений и перегрузку целевых
        # серверов при всплеске нагрузки.
        semaphore_acquired: bool = False
        if not _shutting_down:
            await _delivery_semaphore.acquire()
            semaphore_acquired = True

        # ── HTTP POST (защищённый от отмены) ──────────────────────────
        t0 = datetime.now(timezone.utc)

        async def _http_post() -> httpx.Response:
            """Собственно HTTP-вызов через shared клиент.

            Таймаут передаётся на уровне запроса (не клиента),
            чтобы один shared client обслуживал запросы с разными
            таймаутами.

            ``shutdown_waits_for`` гарантирует,
            что этот таск не будет отменён даже при CancelledError
            в нашем APScheduler-контейнере.
            """
            client = _get_http_client()
            return await _http_post_with_cb(
                client,
                url,
                headers_dict,
                body,
                timeout,
            )

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
            _check_permanent_failure(
                schedule_id,
                message_id,
                destination,
                url,
                trace_id,
            )
            return  # APScheduler повторит по IntervalTrigger

        except CircuitBreakerOpen as exc:
            CircuitBreakerOpenEvent(
                schedule_id=schedule_id,
                destination=destination,
                url=url,
                error=_short_exc(exc),
            ).emit()
            # НЕ вызываем _check_permanent_failure — circuit breaker
            # временный, APScheduler повторит позже.
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

        # Cleanup DLQ tracking — задача выполнена (C3 memory leak fix)
        _cleanup_schedule_tracking(schedule_id)

    finally:
        _in_flight.discard(current_task)
        if semaphore_acquired:
            _delivery_semaphore.release()


# ---------------------------------------------------------------------------
# Ожидание завершения in-flight доставок (вызывается из shutdown)
# ---------------------------------------------------------------------------


async def wait_for_in_flight(timeout: float | None = None) -> None:
    """Дождаться завершения всех in-flight доставок.

    Вызывается из shutdown-последовательности **до** того как
    APScheduler остановит свои task group-и.
    """
    if timeout is None:
        timeout = float(settings.SHUTDOWN_TIMEOUT)
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

    # Сохраняем end_time для DLQ-детекции
    _schedule_end_times[schedule_id] = end

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


def _cleanup_schedule_tracking(schedule_id: str) -> None:
    """Clean up DLQ tracking data for a completed schedule.

    Вызывается при успешной доставке. Предотвращает утечку памяти
    (C3 fix: ``_schedule_end_times`` и ``_attempt_counts``).
    """
    _schedule_end_times.pop(schedule_id, None)
    _attempt_counts.pop(schedule_id, None)


def _check_permanent_failure(
    schedule_id: str,
    message_id: str,
    destination: str,
    url: str,
    trace_id: str | None,
) -> None:
    """Проверить, исчерпан ли TTL. Если да — ``DeliveryExpiredEvent``.

    Вызывается из error-handler'ов ``deliver_payload`` перед ``return``.
    Если ``end_time`` в прошлом, а HTTP всё ещё не 2xx — это permanent
    failure (аналог DLQ).

    На DLQ также чистим tracking (C3 memory leak fix).
    """
    from .events import DeliveryExpiredEvent

    end_time = _schedule_end_times.get(schedule_id)
    if end_time is None:
        return
    if datetime.now(timezone.utc) < end_time:
        return  # ещё есть попытки

    attempts = _attempt_counts.get(schedule_id, 0)
    DeliveryExpiredEvent(
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        message_id=message_id,
        trace_id=trace_id,
        pause=0,
        ttl=0,
        attempts=attempts,
    ).emit()

    # Cleanup: задача завершена (DLQ), чистим tracking (C3)
    _cleanup_schedule_tracking(schedule_id)


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
