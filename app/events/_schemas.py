"""Centralised log event definitions.

Каждое событие логирования — **Pydantic-модель** с методом ``.emit()``.
Никаких ``logger.info("event_name", …)`` в остальном коде — только
конструктор модели + ``.emit()``::

    DeliveryAttemptEvent(
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        headers=headers,
        body_size=body_size,
        body=body,
        timeout=timeout,
    ).emit()

Поля, общие для нескольких событий, вынесены в базовые классы-примеси
и переиспользуются через множественное наследование::

    LogEvent                   ← dt, ulid, .emit(), _level
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
    ├── PayloadReceivedEvent          = MessageRef + TargetRef + ScheduleRef
    │   └── PayloadReceivedAMQPEvent  + 1C audit fields
    │
    └── Остальные — standalone (нет пересечений полей)

Принадлежит модулю ``app.events._schemas``, re-export через ``app.events``.
Имя события ``event`` в JSON-строке вычисляется автоматически
из имени класса (``CamelCase → snake_case``, с отрезанным ``Event``).

Для событий без собственных полей используйте ``LogEvent()`` напрямую
и передайте имя события через параметр ``event`` в ``.emit()``::

    LogEvent().emit(event="service_startup")
    LogEvent().emit(event="stderr_reader_error", level="error")
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel, Field, NonNegativeInt, PositiveFloat, PositiveInt
from pydantic.types import PastDatetime
from ulid import ULID

# ── Lifecycle event names that are skipped in production ────────────────────
# Bare ``LogEvent().emit(event="service_startup")`` calls use these names.
_LIFECYCLE_EVENTS: frozenset[str] = frozenset({
    "service_startup",
    "shutdown_amqp_stopped",
    "shutdown_deliveries_resolved",
    "shutdown_complete",
})

__all__ = [
    "CircuitBreakerOpenEvent",
    "DeliveryAttemptEvent",
    "DeliveryEventBase",
    "DeliveryExpiredEvent",
    "DeliveryFailedEvent",
    "DeliveryHttpErrorEvent",
    "DeliveryResponseEvent",
    "DeliveryScheduledEvent",
    "DeliverySuccessEvent",
    "FatalErrorEvent",
    "HandlerFailedEvent",
    "LogEvent",
    "MessageRef",
    "PayloadReceivedAMQPEvent",
    "PayloadReceivedEvent",
    "ScheduleRef",
    "SchedulerStartedEvent",
    "ShutdownCancelledEvent",
    "ShutdownTimeoutEvent",
    "ShutdownWaitingEvent",
    "TargetRef",
    "UnhandledTaskErrorEvent",
]


# ===================================================================
# Helpers
# ===================================================================


def _event_name_for(cls: type) -> str:
    """Derive ``"delivery_attempt"`` from ``DeliveryAttemptEvent``.

    Strips trailing ``Event`` suffix, then converts ``CamelCase``
    to ``snake_case`` (acronym-aware: ``AMQP → amqp``).
    """
    name = cls.__name__
    name = name.removesuffix("Event")
    # Split on:
    #   1. lower→upper boundary       (attempt → Attempt)
    #   2. upper→upper+lower boundary (AMQP → Event)
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        name,
    ).lower()


# ===================================================================
# Pydantic models with .emit()
# ===================================================================


class LogEvent(BaseModel):
    """Base for all log events.

    - ``extra='forbid'`` → typo in field name = Pydantic error.
    - ``validate_default=True`` → even defaults are type-checked.
    - ``.emit()`` → validates, serialises, and writes to stdout (JSONL).

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
    _level: ClassVar[str] = "info"
    _prod_skip: ClassVar[bool] = False  # True on lifecycle events, hidden in prod

    def emit(
        self,
        event: str | None = None,
        level: str | None = None,
        **extra: object,
    ) -> None:
        """Validate, serialize and write to stdout (JSONL).

        1. ``model_dump(mode='json', exclude_none=True)`` — сериализует
           datetime → ISO-8601, ULID → 26-символьная строка.
        2. Добавляет ``level`` (из ``_level`` или переданный вручную).
        3. Добавляет ``model`` (имя класса) и ``event``, если передан явно.
        4. Любые ``**extra`` поля мержатся поверх (для событий без модели).
        5. ``json.dumps`` + ``os.write(1, …)``.

        **ВНИМАНИЕ:** emit() не трансформирует данные.
        Никакой PII-маскировки или инжекции context vars здесь нет.
        """
        import json as json_mod
        import os

        # Production: skip lifecycle events (startup, shutdown, etc.)
        if not __debug__:
            event_name = event if event is not None else _event_name_for(type(self))
            if self._prod_skip or event_name in _LIFECYCLE_EVENTS:
                return

        from app.config import settings

        data = self.model_dump(mode="json", exclude_none=True)
        data["level"] = level if level is not None else self._level
        data["model"] = type(self).__name__
        if event is not None:
            data["event"] = event
        data.update(extra)

        indent = 2 if settings.PRETTY_LOG else None
        line = json_mod.dumps(data, default=str, indent=indent) + "\n"

        try:
            os.write(1, line.encode("utf-8", errors="replace"))
        except OSError:
            pass


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


# ── Delivery chain base ────────────────────────────────────────────────


class DeliveryEventBase(ScheduleRef, TargetRef):
    """``schedule_id`` + ``destination`` + ``url`` — три поля,
    присутствующие во всех событиях цикла доставки."""

    pass


# ── Delivery chain (events fired inside ``deliver_payload``) ───────────


class DeliveryAttemptEvent(DeliveryEventBase):
    """Попытка HTTP POST: тело запроса, размер, таймаут."""

    headers: list[tuple[str, str]] | None = None
    body_size: NonNegativeInt | None = None
    body: str | None = None
    timeout: PositiveInt | None = None


class DeliveryResponseEvent(DeliveryEventBase):
    """HTTP-ответ получен. **Логируется ДО raise_for_status**."""

    status_code: int | None = Field(default=None, ge=100, lt=600)
    response_headers: dict[str, str] | None = None
    response_body: str | None = None
    duration_ms: NonNegativeInt | None = None


class DeliverySuccessEvent(DeliveryEventBase):
    """Доставка успешна (HTTP 2xx), расписание удаляется."""

    status_code: int | None = Field(default=None, ge=100, lt=600)
    duration_ms: NonNegativeInt | None = None


class DeliveryHttpErrorEvent(DeliveryEventBase):
    """Целевой сервер вернул HTTP-ошибку (4xx/5xx). Будет повтор."""

    status_code: int | None = Field(default=None, ge=100, lt=600)
    error: str | None = None


class DeliveryFailedEvent(DeliveryEventBase):
    """Сетевая ошибка / таймаут. Будет повтор."""

    error: str | None = None
    duration_ms: NonNegativeInt | None = None


class DeliveryScheduledEvent(MessageRef, DeliveryEventBase):
    """Создано APScheduler-расписание с IntervalTrigger.

    Наследует message_id, trace_id от MessageRef
    и schedule_id, destination, url от DeliveryEventBase.
    """

    pause: NonNegativeInt | None = None
    ttl: NonNegativeInt | None = None
    end_time: str | None = None


# ── Payload received ──────────────────────────────────────────────────


class PayloadReceivedEvent(MessageRef, TargetRef, ScheduleRef):
    """Сообщение получено, создано расписание доставки.

    message_id + trace_id     → MessageRef
    destination + url         → TargetRef
    schedule_id               → ScheduleRef
    """

    headers: set[tuple[str, str]] | None = None
    timeout: PositiveInt | None = None
    pause: NonNegativeInt | None = None
    ttl: NonNegativeInt | None = None
    schedule_id: str | None = None  # type: ignore[assignment]


class PayloadReceivedAMQPEvent(PayloadReceivedEvent):
    """Сообщение получено из AMQP (с дополнительными полями аудита 1С).

    ``delivery_count`` — сколько раз AMQP-брокер уже выдавал это сообщение
    (поле ``Header.delivery_count``). Позволяет детектить повторные
    доставки со стороны брокера (не путать с retry-циклом webhooker'а).
    """

    correlation_id: str | None = None
    sender_code: str | None = None
    recipient_code: str | None = None
    integ_message_id: str | None = None
    delivery_count: NonNegativeInt | None = None


# ── Handler / Errors ──────────────────────────────────────────────────


class HandlerFailedEvent(LogEvent):
    """Ошибка парсинга AMQP-сообщения, сообщение отклонено.

    Содержит ``body_preview`` (первые N байт сырого тела) и ``body_size``
    для диагностики того, что именно прислала 1С.
    """

    _level: ClassVar[str] = "error"
    destination: str
    error: str
    body_size: NonNegativeInt | None = None
    body_preview: str | None = None


# ── Scheduler ─────────────────────────────────────────────────────────


class SchedulerStartedEvent(LogEvent):
    """APScheduler запущен в фоне."""

    _prod_skip: ClassVar[bool] = True
    max_concurrent: PositiveInt


# ── Shutdown ──────────────────────────────────────────────────────────


class ShutdownWaitingEvent(LogEvent):
    """Ожидание завершения активных HTTP-доставок."""

    _prod_skip: ClassVar[bool] = True
    count: NonNegativeInt
    timeout: PositiveFloat


class ShutdownTimeoutEvent(LogEvent):
    """Таймаут ожидания — ``remaining`` задач не завершились."""

    _prod_skip: ClassVar[bool] = True
    remaining: NonNegativeInt
    timeout: PositiveFloat


class ShutdownCancelledEvent(LogEvent):
    """Зависшие доставки принудительно отменены."""

    _prod_skip: ClassVar[bool] = True
    count: NonNegativeInt


class FatalErrorEvent(LogEvent):
    """Фатальная ошибка при запуске приложения."""

    _level: ClassVar[str] = "critical"
    error: str


class UnhandledTaskErrorEvent(LogEvent):
    """Необработанная ошибка в фоновой asyncio-задаче (safe_create_task).

    Срабатывает при любом исключении, кроме ``CancelledError``,
    в обёртке ``safe_create_task._wrapped()``.
    """

    _level: ClassVar[str] = "error"
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

    _level: ClassVar[str] = "warning"
    error: str


class DeliveryExpiredEvent(MessageRef, DeliveryEventBase):
    """Доставка окончательно провалена — исчерпан TTL.

    Все retry-попытки по IntervalTrigger закончились,
    целевой сервер так и не ответил 2xx.
    Это аналог Dead Letter Queue (DLQ) — сообщение требует
    ручного анализа.

    message_id + trace_id → MessageRef
    schedule_id           → ScheduleRef
    destination + url     → TargetRef
    """

    _level: ClassVar[str] = "warning"
    attempt_count: NonNegativeInt
    pause: NonNegativeInt
    ttl: NonNegativeInt
