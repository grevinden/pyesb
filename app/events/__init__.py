"""Logging output — JSONL via stdlib logging + Pydantic модели.

Usage::

    from app.events import SomeEvent
    SomeEvent(...).emit()

Все Pydantic-модели событий re-export-ятся из ``._schemas``.
Stdlib-логи (APScheduler, uvicorn) проходят через ``logging.yaml``
с форматером ``app.events.JsonlFormatter``, который использует
Pydantic-модель ``LogEvent`` напрямую.

Для stderr redirect (Rust tracing из pyesb-amqp) stderr-пайп
читается в фоновом таске и отправляется через ``logging.getLogger("pyesb_amqp")``.

**ВНИМАНИЕ:** events/ не трансформирует поступившие данные.
Никакой PII-маскировки, санитизации заголовков или инжекции context vars.
Это ответственность слоя выше (events.py или middleware).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from ._formatter import JsonlFormatter
from ._schemas import (
    CircuitBreakerOpenEvent,
    DeliveryAttemptEvent,
    DeliveryEventBase,
    DeliveryExpiredEvent,
    DeliveryFailedEvent,
    DeliveryHttpErrorEvent,
    DeliveryResponseEvent,
    DeliveryScheduledEvent,
    DeliverySuccessEvent,
    FatalErrorEvent,
    HandlerFailedEvent,
    LogEvent,
    MessageRef,
    PayloadReceivedAMQPEvent,
    PayloadReceivedEvent,
    ScheduleRef,
    SchedulerStartedEvent,
    ShutdownCancelledEvent,
    ShutdownTimeoutEvent,
    ShutdownWaitingEvent,
    TargetRef,
    UnhandledTaskErrorEvent,
)
from ._stderr import redirect_stderr, restore_stderr, stderr_to_jsonl

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
    "JsonlFormatter",
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
    "stderr_redirect_lifespan",
]


@asynccontextmanager
async def stderr_redirect_lifespan() -> AsyncGenerator[None, None]:
    """Context manager that redirects stderr -> JSONL during its lifetime.

    Use inside the FastAPI ``lifespan``::

        @asynccontextmanager
        async def lifespan(app):
            async with stderr_redirect_lifespan():
                yield
    """
    r_fd, original_fd = redirect_stderr()
    task: asyncio.Task[None] | None = None
    try:
        task = asyncio.create_task(stderr_to_jsonl(r_fd), name="stderr-to-jsonl")
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, StopIteration):
                pass
        restore_stderr(r_fd, original_fd)
