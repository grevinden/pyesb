"""Lifespan management for FastAPI — APScheduler + AMQP lifecycle.

Shutdown sequence:

1. FastAPI перестаёт принимать HTTP (встроено в uvicorn).
2. ``AmqpServer`` закрывает соединения (выход из стека).
3. ``shutdown_guard``: ``_shutting_down = True``, ``wait_for_in_flight()``.
4. ``AsyncScheduler`` останавливается (выход из стека).
5. ``close_http_client()`` — закрытие пула httpx.
6. ``close_db()``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

__all__ = [
    "lifespan",
]

from apscheduler import AsyncScheduler, TaskDefaults
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from fastapi import FastAPI
from pyesb_amqp import AmqpMessage, AmqpServer

from .config import settings
from .database import close_db, get_engine, setup_db
from .delivery import close_http_client, create_delivery_schedule
from .events import (
    HandlerFailedEvent,
    PayloadReceivedAMQPEvent,
    SchedulerStartedEvent,
    ServiceStartupEvent,
    ShutdownAmqpStoppedEvent,
    ShutdownCompleteEvent,
    ShutdownDeliveriesResolvedEvent,
    fmt_headers,
)
from .log import (
    load_logging_config,
    start_logging_queue,
    stderr_redirect_lifespan,
    stop_logging_queue,
)
from .middleware import MetricsMiddleware
from .models import Message
from .router import first_str, resolve_trace_id


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет жизненным циклом APScheduler и AMQP.

    Shutdown sequence:

    1. FastAPI перестаёт принимать HTTP (встроено в uvicorn).
    2. ``AmqpServer`` закрывает соединения (выход из стека).
    3. ``shutdown_guard``: ``_shutting_down = True``, ``wait_for_in_flight()``.
    4. ``AsyncScheduler`` останавливается (выход из стека).
    5. ``close_http_client()`` — закрытие пула httpx.
    6. ``close_db()``.
    """
    load_logging_config()
    start_logging_queue()
    await setup_db()
    ServiceStartupEvent().emit()

    metrics = MetricsMiddleware()

    @asynccontextmanager
    async def _shutdown_guard() -> AsyncGenerator[None, None]:
        from .delivery import _shutting_down, wait_for_in_flight

        try:
            yield
        finally:
            _shutting_down = True
            ShutdownAmqpStoppedEvent().emit()
            await wait_for_in_flight(timeout=float(settings.SHUTDOWN_TIMEOUT))
            ShutdownDeliveriesResolvedEvent().emit()

    async with AsyncExitStack() as exit_stack:
        # ── 1. Scheduler (exits LAST) ─────────────────────────────────
        scheduler = AsyncScheduler(
            data_store=SQLAlchemyDataStore(get_engine()),
            max_concurrent_jobs=settings.SCHEDULER_MAX_CONCURRENT,
            task_defaults=TaskDefaults(max_running_jobs=None),
        )
        await exit_stack.enter_async_context(scheduler)
        await scheduler.start_in_background()
        SchedulerStartedEvent(max_concurrent=settings.SCHEDULER_MAX_CONCURRENT).emit()

        # ── 2. Shutdown guard (exits BETWEEN AMQP and Scheduler) ──────
        await exit_stack.enter_async_context(_shutdown_guard())

        # ── 3. AMQP handler (closure над scheduler / logger) ──────────
        async def amqp_handler(destination: str, msg: AmqpMessage) -> bool:
            try:
                parsed = Message.model_validate(
                    msg, from_attributes=True, context={"destination": destination}
                )
                ps = parsed.payload
                message_id = str(parsed.properties.message_id)
                # Дополнительные поля для аудита
                correlation_id = (
                    str(parsed.properties.correlation_id)
                    if parsed.properties.correlation_id
                    else None
                )
                _props = parsed.application_properties
                sender_code = first_str(_props.integ_sender_code)
                recipient_code = first_str(_props.integ_recipient_code)
                integ_message_id = str(_props.integ_message_id)

                # ── delivery_count: сколько раз AMQP-брокер уже выдавал сообщение ──
                delivery_count = parsed.header.delivery_count

                # ── trace_id: из тела сообщения, либо из заголовка X-Trace-Id ──
                trace_id = resolve_trace_id(ps.trace_id, ps.headers)

                schedule_id = await create_delivery_schedule(
                    scheduler,
                    destination=destination,
                    url=str(ps.url),
                    body=ps.body,
                    headers=list(ps.headers) if ps.headers else None,
                    timeout=ps.timeout,
                    pause=ps.pause,
                    ttl=ps.ttl,
                    trace_id=trace_id,
                    message_id=message_id,
                )

                PayloadReceivedAMQPEvent(
                    message_id=message_id,
                    correlation_id=correlation_id,
                    sender_code=sender_code,
                    recipient_code=recipient_code,
                    integ_message_id=integ_message_id,
                    delivery_count=delivery_count,
                    destination=destination,
                    url=str(ps.url),
                    headers=fmt_headers(ps.headers),
                    timeout=ps.timeout,
                    pause=ps.pause,
                    ttl=ps.ttl,
                    trace_id=trace_id,
                    schedule_id=schedule_id,
                ).emit()
                return True
            except Exception as e:
                HandlerFailedEvent(
                    destination=destination,
                    error=f"{type(e).__name__}: {e}",
                ).emit()
                return False

        # ── 4. AMQP + stderr (exit FIRST) ─────────────────────────────
        await exit_stack.enter_async_context(stderr_redirect_lifespan())
        await exit_stack.enter_async_context(AmqpServer(handler=amqp_handler))

        # ── 5. Фиксируем scheduler и metrics в app.state ───────────────
        # Используем module-level app (oidc_add_routes wrapper),
        # т.к. request.app при обращении из эндпоинта — это враппер,
        # а не оригинальный FastAPI (_app).
        from .main import (
            app,  # lazy import — избегаем циклического импорта  # noqa: F811
        )

        app.state.scheduler = scheduler
        app.state.metrics = metrics
        yield

    # ── После выхода из стека: scheduler остановлен ────────────────────
    await close_http_client()
    await close_db()
    ShutdownCompleteEvent().emit()
    stop_logging_queue()
