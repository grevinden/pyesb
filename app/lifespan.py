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
from pyesb_amqp import AmqpServer

from app.config import bootstrap, settings
from app.config._database import close_db, get_engine

from .delivery.client import close_http_client
from .delivery.semaphore import set_shutting_down, wait_for_in_flight
from .events import (
    LogEvent,
    SchedulerStartedEvent,
    stderr_redirect_lifespan,
)
from .ingress.amqp import amqp_handler, set_scheduler


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
    bootstrap()
    LogEvent().emit(event="service_startup")

    @asynccontextmanager
    async def _shutdown_guard() -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            set_shutting_down()
            LogEvent().emit(event="shutdown_amqp_stopped")
            await wait_for_in_flight(timeout=float(settings.SHUTDOWN_TIMEOUT))
            LogEvent().emit(event="shutdown_deliveries_resolved")

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

        # ── 2. Set scheduler for AMQP handler ─────────────────────────
        set_scheduler(scheduler)

        # ── 3. Shutdown guard (exits BETWEEN AMQP and Scheduler) ──────
        await exit_stack.enter_async_context(_shutdown_guard())

        # ── 4. AMQP + stderr (exit FIRST) ─────────────────────────────
        await exit_stack.enter_async_context(stderr_redirect_lifespan())
        await exit_stack.enter_async_context(AmqpServer(handler=amqp_handler))

        # ── 5. Фиксируем scheduler в app.state ────────────────────────
        # Используем module-level app (oidc_add_routes wrapper),
        # т.к. request.app при обращении из эндпоинта — это враппер,
        # а не оригинальный FastAPI (_app).
        from .main import (
            app,  # lazy import — избегаем циклического импорта  # noqa: F811
        )

        app.state.scheduler = scheduler
        yield

    # ── После выхода из стека: scheduler остановлен ────────────────────
    await close_http_client()
    await close_db()
    LogEvent().emit(event="shutdown_complete")
