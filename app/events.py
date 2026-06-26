"""Centralised log event definitions.

Каждое событие логирования — **Pydantic-модель** с методом ``.emit()``.
Никаких ``logger.info("event_name", …)`` в остальном коде — только
конструктор модели + ``.emit()``::

    DeliveryAttemptEvent(
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        headers=fmt_headers(headers),
        body_size=body_size,
        body=body,
        timeout=timeout,
    ).emit()

Поля, общие для нескольких событий, вынесены в базовые классы-примеси
и переиспользуются через множественное наследование::

    LogEvent                   ← dt, ulid, .emit(), _event_name, _level
    ├── ScheduleRef            (schedule_id)
    ├── TargetRef              (destination, url)
    ├── MessageRef             (message_id, trace_id)
    │
    ├── DeliveryEventBase = ScheduleRef + TargetRef
    │   ├── DeliveryAttemptEvent       + headers, body_size, body, timeout
    │   ├── DeliveryResponseEvent      + status_code, response_headers, …
    │   ├── DeliverySuccessEvent       + status_code, duration_ms
    │   ├── DeliveryHttpErrorEvent     + status_code, error
    │   ├── DeliveryFailedEvent        + error, duration_ms
    │   └── DeliveryScheduledEvent     + MessageRef + pause, ttl, end_time
    │
    ├── DeliverySkippedShutdownEvent = MessageRef + TargetRef
    ├── ScheduleRemoveSkippedEvent    = ScheduleRef (только schedule_id)
    ├── PayloadReceivedEvent          = MessageRef + TargetRef + ScheduleRef
    │   └── PayloadReceivedAMQPEvent  + 1C audit fields
    │
    └── Остальные — standalone (нет пересечений полей)
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, Field
from pydantic.types import PastDatetime
from ulid import ULID

__all__ = [
    "CircuitBreakerOpenEvent",
    "DeliveryAttemptEvent",
    "DeliveryEventBase",
    "DeliveryExpiredEvent",
    "DeliveryFailedEvent",
    "DeliveryHttpErrorEvent",
    "DeliveryResponseEvent",
    "DeliveryScheduledEvent",
    "DeliverySkippedShutdownEvent",
    "DeliverySuccessEvent",
    "FatalErrorEvent",
    "HandlerFailedEvent",
    "LogEvent",
    "MessageRef",
    "PayloadReceivedAMQPEvent",
    "PayloadReceivedEvent",
    "ScheduleRef",
    "ScheduleRemoveSkippedEvent",
    "SchedulerStartedEvent",
    "ServiceStartupEvent",
    "ShutdownAmqpStoppedEvent",
    "ShutdownCancelledEvent",
    "ShutdownCompleteEvent",
    "ShutdownDeliveriesCompletedEvent",
    "ShutdownDeliveriesResolvedEvent",
    "ShutdownTimeoutEvent",
    "ShutdownWaitingEvent",
    "StderrReaderErrorEvent",
    "TargetRef",
    "UnhandledTaskErrorEvent",
    "exc_info",
    "fmt_headers",
]

_logger = structlog.get_logger("events")

# ===================================================================
# Pydantic models with .emit()
# ===================================================================


class LogEvent(BaseModel):
    """Base for all log events.

    - ``extra='forbid'`` → typo in field name = Pydantic error.
    - ``validate_default=True`` → even defaults are type-checked.
    - ``.emit()`` → validates, serialises, and sends to structlog.

    Каждое событие несёт два обязательных поля:
    * ``dt`` — PastDatetime, метка времени события (автогенерируется).
    * ``ulid`` — ULID, уникальный идентификатор события (автогенерируется).
    """

    model_config = {"extra": "forbid", "validate_default": True}

    # ── Обязательные поля каждого события ────────────────────────────
    dt: PastDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Метка времени события (автоматически, в прошлом)",
    )
    ulid: ULID = Field(
        default_factory=ULID,
        description="Уникальный идентификатор события (ULID v1)",
    )

    # Metadata — NOT fields (ClassVar is excluded from model_dump)
    _event_name: ClassVar[str] = "unknown"
    _level: ClassVar[str] = "info"

    def emit(self) -> None:
        """Validate and log this event through structlog.

        1. ``model_dump(mode='json')`` — сериализует datetime → ISO-8601,
           ULID → 26-символьная строка.
        2. Pydantic уже проверил все поля при конструировании.
        3. Structlog processors добавляют ``level``, ``timestamp``,
           ``message_id``, ``trace_id`` (через ``_add_context_vars``).
        """
        log_fn = getattr(_logger, self._level, _logger.info)
        log_fn(self._event_name, **self.model_dump(mode="json"))


# ── Field-group mixins (single source of truth) ────────────────────────


class ScheduleRef(LogEvent):
    """Ссылка на расписание доставки (APScheduler schedule_id)."""

    schedule_id: str


class TargetRef(LogEvent):
    """Цель доставки (куда отправлять HTTP POST)."""

    destination: str
    url: str


class MessageRef(LogEvent):
    """Идентификация сообщения (сквозной ID + опциональный trace_id)."""

    message_id: str
    trace_id: str | None = None


# ── Delivery chain (events fired inside ``deliver_payload``) ───────────


class DeliveryEventBase(ScheduleRef, TargetRef):
    """``schedule_id`` + ``destination`` + ``url`` — три поля,
    присутствующие во всех событиях цикла доставки."""

    pass


class DeliveryAttemptEvent(DeliveryEventBase):
    """Попытка HTTP POST: тело запроса, размер, таймаут."""

    _event_name: ClassVar[str] = "delivery_attempt"
    _level: ClassVar[str] = "info"
    headers: list[list[str]] | None = None
    body_size: int | None = None
    body: str | None = None
    timeout: int


class DeliveryResponseEvent(DeliveryEventBase):
    """HTTP-ответ получен. **Логируется ДО raise_for_status**."""

    _event_name: ClassVar[str] = "delivery_response"
    _level: ClassVar[str] = "info"
    status_code: int
    response_headers: dict[str, str]
    response_body: str | None = None
    duration_ms: int


class DeliverySuccessEvent(DeliveryEventBase):
    """Доставка успешна (HTTP 2xx), расписание удаляется."""

    _event_name: ClassVar[str] = "delivery_success"
    _level: ClassVar[str] = "info"
    status_code: int
    duration_ms: int


class DeliveryHttpErrorEvent(DeliveryEventBase):
    """Целевой сервер вернул HTTP-ошибку (4xx/5xx). Будет повтор."""

    _event_name: ClassVar[str] = "delivery_http_error"
    _level: ClassVar[str] = "warning"
    status_code: int
    error: str


class DeliveryFailedEvent(DeliveryEventBase):
    """Сетевая ошибка / таймаут. Будет повтор."""

    _event_name: ClassVar[str] = "delivery_failed"
    _level: ClassVar[str] = "error"
    error: str
    duration_ms: int | None = None


class DeliveryScheduledEvent(DeliveryEventBase, MessageRef):
    """Создано APScheduler-расписание с IntervalTrigger.

    Наследует schedule_id, destination, url от DeliveryEventBase
    и message_id, trace_id от MessageRef.
    """

    _event_name: ClassVar[str] = "delivery_scheduled"
    _level: ClassVar[str] = "info"
    pause: int
    ttl: int
    end_time: str


class DeliverySkippedShutdownEvent(MessageRef, TargetRef):
    """Доставка пропущена — приложение выключается (``_shutting_down``).

    Все поля (message_id, trace_id, destination, url) — от предков.
    """

    _event_name: ClassVar[str] = "delivery_skipped_shutdown"
    _level: ClassVar[str] = "warning"
    pass


class ScheduleRemoveSkippedEvent(ScheduleRef):
    """Расписание уже удалено (гонка при remove_schedule).

    Единственное поле schedule_id — от ScheduleRef.
    """

    _event_name: ClassVar[str] = "schedule_remove_skipped"
    _level: ClassVar[str] = "debug"
    pass


# ── Payload received ──────────────────────────────────────────────────


class PayloadReceivedEvent(MessageRef, TargetRef, ScheduleRef):
    """Сообщение получено, создано расписание доставки.

    message_id + trace_id     → MessageRef
    destination + url         → TargetRef
    schedule_id               → ScheduleRef
    """

    _event_name: ClassVar[str] = "payload_received"
    _level: ClassVar[str] = "info"
    headers: list[list[str]] | None = None
    timeout: int
    pause: int
    ttl: int


class PayloadReceivedAMQPEvent(PayloadReceivedEvent):
    """Сообщение получено из AMQP (с дополнительными полями аудита 1С).

    ``delivery_count`` — сколько раз AMQP-брокер уже выдавал это сообщение
    (поле ``Header.delivery_count``). Позволяет детектить повторные
    доставки со стороны брокера (не путать с retry-циклом webhooker'а).
    """

    _event_name: ClassVar[str] = "payload_received"
    _level: ClassVar[str] = "info"
    correlation_id: str | None = None
    sender_code: str | None = None
    recipient_code: str | None = None
    integ_message_id: str
    delivery_count: int


# ── Handler / Errors ──────────────────────────────────────────────────


class HandlerFailedEvent(LogEvent):
    """Ошибка парсинга AMQP-сообщения, сообщение отклонено."""

    _event_name: ClassVar[str] = "handler_failed"
    _level: ClassVar[str] = "error"
    destination: str
    error: str


# ── Scheduler ─────────────────────────────────────────────────────────


class SchedulerStartedEvent(LogEvent):
    """APScheduler запущен в фоне."""

    _event_name: ClassVar[str] = "scheduler_started"
    _level: ClassVar[str] = "info"
    max_concurrent: int


# ── Shutdown ──────────────────────────────────────────────────────────


class ShutdownWaitingEvent(LogEvent):
    """Ожидание завершения активных HTTP-доставок."""

    _event_name: ClassVar[str] = "shutdown: waiting_for_deliveries"
    _level: ClassVar[str] = "info"
    count: int
    timeout: float


class ShutdownTimeoutEvent(LogEvent):
    """Таймаут ожидания — ``remaining`` задач не завершились."""

    _event_name: ClassVar[str] = "shutdown: deliveries_timeout"
    _level: ClassVar[str] = "warning"
    remaining: int
    timeout: float


class ShutdownCancelledEvent(LogEvent):
    """Зависшие доставки принудительно отменены."""

    _event_name: ClassVar[str] = "shutdown: deliveries_cancelled"
    _level: ClassVar[str] = "info"
    count: int


class ShutdownAmqpStoppedEvent(LogEvent):
    """AMQP-транспорт остановлен; ``_shutting_down = True``."""

    _event_name: ClassVar[str] = "shutdown: amqp_stopped"
    _level: ClassVar[str] = "info"
    pass


class ShutdownDeliveriesResolvedEvent(LogEvent):
    """Все in-flight задачи разрешены — можно останавливать APScheduler."""

    _event_name: ClassVar[str] = "shutdown: deliveries_resolved"
    _level: ClassVar[str] = "info"
    pass


class ShutdownDeliveriesCompletedEvent(LogEvent):
    """Все активные доставки завершились штатно."""

    _event_name: ClassVar[str] = "shutdown: deliveries_completed"
    _level: ClassVar[str] = "info"
    pass


class ServiceStartupEvent(LogEvent):
    """Приложение запущено, lifespan начался."""

    _event_name: ClassVar[str] = "service_startup"
    _level: ClassVar[str] = "info"
    pass


class ShutdownCompleteEvent(LogEvent):
    """Все компоненты остановлены, приложение завершило работу."""

    _event_name: ClassVar[str] = "shutdown: complete"
    _level: ClassVar[str] = "info"
    pass


class StderrReaderErrorEvent(LogEvent):
    """Неожиданная ошибка в stderr-reader (Rust tracing pyesb-amqp), перезапуск."""

    _event_name: ClassVar[str] = "stderr_to_jsonl_error, restarting"
    _level: ClassVar[str] = "exception"
    pass


class FatalErrorEvent(LogEvent):
    """Фатальная ошибка при запуске приложения."""

    _event_name: ClassVar[str] = "fatal_error"
    _level: ClassVar[str] = "exception"
    error: str


class UnhandledTaskErrorEvent(LogEvent):
    """Необработанная ошибка в фоновой asyncio-задаче (safe_create_task).

    Срабатывает при любом исключении, кроме ``CancelledError``,
    в обёртке ``safe_create_task._wrapped()``.
    """

    _event_name: ClassVar[str] = "unhandled_task_error"
    _level: ClassVar[str] = "exception"
    task_name: str | None = None


class CircuitBreakerOpenEvent(DeliveryEventBase):
    """Circuit breaker разомкнут — HTTP-доставка на URL приостановлена.

    Целевой сервер временно недоступен (>=10 ошибок за последнюю минуту).
    Доставка на этот URL приостанавливается на ``ttl`` (5 минут по умолчанию),
    после чего circuit breaker переходит в half-open состояние
    и пропускает один запрос для проверки.

    APScheduler продолжит попытки, circuit breaker сам восстановится.
    Это НЕ permanent failure (``DeliveryExpiredEvent`` будет отдельно,
    если TTL истёк, а сервер всё ещё недоступен).
    """

    _event_name: ClassVar[str] = "circuit_breaker_open"
    _level: ClassVar[str] = "warning"
    error: str


class DeliveryExpiredEvent(ScheduleRef, TargetRef, MessageRef):
    """Доставка окончательно провалена — исчерпан TTL.

    Все retry-попытки по IntervalTrigger закончились,
    целевой сервер так и не ответил 2xx.
    Это аналог Dead Letter Queue (DLQ) — сообщение требует
    ручного анализа.
    """

    _event_name: ClassVar[str] = "delivery_expired"
    _level: ClassVar[str] = "warning"
    pause: int
    ttl: int
    error: str | None = None
    attempts: int | None = None


# ===================================================================
# Helpers
# ===================================================================


def fmt_headers(
    headers: Iterable[tuple[str, str]] | None,
) -> list[list[str]] | None:
    """Convert ``[(k, v), …]`` to ``[[k, v], …]`` for JSON logging.

    Public helper — call before passing to any model with ``headers`` field::

        DeliveryAttemptEvent(
            headers=fmt_headers(raw_headers),
            ...
        ).emit()
    """
    if headers is None:
        return None
    return [list(h) for h in headers]


def exc_info() -> dict[str, Any]:
    """Return current exception info (for manual ``logger.exception`` calls)."""
    import sys

    return {"exc_info": sys.exc_info()}
