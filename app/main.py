"""1C ESB Gateway — FastAPI + APScheduler delivery + async SQLite.

Все события доставки пишутся в JSONL через structlog.
БД (``data.db``) содержит только APScheduler-таблицы — мелкая, не пухнет.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from uuid import UUID, uuid4

from apscheduler import AsyncScheduler, TaskDefaults
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, HttpUrl, Json, PositiveInt
from pyesb_amqp import AmqpMessage, AmqpServer, E1CMessage
from pyesb_amqp.oidc import ChannelDesription
from pyesb_amqp.oidc import add_routes as oidc_add_routes

from .config import settings
from .database import close_db, get_engine
from .events import (
    HandlerFailedEvent,
    PayloadReceivedAMQPEvent,
    PayloadReceivedEvent,
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
from .router import first_str, resolve_trace_id

# ---------------------------------------------------------------------------
# Архитектура приёма сообщений
#
# 1. 1С запрашивает OIDC metadata → получает список каналов
#    (process + channel).
# 2. На стороне 1С администратор связывает приложение+канал
#    с именем очереди (destination).
# 3. При отправке 1С кладёт routing-key = destination.
#    amqp_handler(destination, msg) получает destination из routing key.
#
# HTTP POST / — альтернатива без OIDC, destination="http".
# ---------------------------------------------------------------------------


class PayloadSchema(BaseModel):
    """Уведомление для доставки на внешний URL.

    Тот же формат используется при отправке из 1С через AMQP
    (body AMQP-сообщения — JSON, соответствующий этой схеме).
    """

    url: HttpUrl
    body: dict | list | None = None
    headers: set[tuple[str, str]] | None = None
    timeout: PositiveInt
    pause: PositiveInt
    ttl: PositiveInt
    trace_id: UUID | None = None


class Message(E1CMessage):
    """AMQP-сообщение, где body (JSON) парсится через Pydantic."""

    payload: Json[PayloadSchema] = Field(validation_alias="body")


# ---------------------------------------------------------------------------
# Lifespan — запуск / остановка APScheduler + AMQP
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет жизненным циклом APScheduler и AMQP.

    Shutdown sequence:
    1. FastAPI перестаёт принимать HTTP (встроено в uvicorn).
    2. ``AmqpServer`` закрывает соединения (выход из стека).
    3. ``shutdown_guard``: ``_shutting_down = True``, ``wait_for_in_flight()``.
    4. ``AsyncScheduler`` останавливается (выход из стека).
    5. ``close_db()``.
    """
    load_logging_config()
    start_logging_queue()  # неблокирующее логирование через QueueHandler
    ServiceStartupEvent().emit()

    from .delivery import create_delivery_schedule
    from .middleware import MetricsMiddleware

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
        app.state.scheduler = scheduler  # noqa: F821 — module-level app
        app.state.metrics = metrics  # noqa: F821 — для GET /metrics
        yield

    # ── После выхода из стека: scheduler остановлен ────────────────────
    await close_db()
    ShutdownCompleteEvent().emit()
    stop_logging_queue()  # flush всех оставшихся записей


# ---------------------------------------------------------------------------
# App — FastAPI инстанс
# ---------------------------------------------------------------------------

app = oidc_add_routes(
    ChannelDesription(
        access="WRITE_ONLY",
        process="process1",
        channel="channel1",
        destination="destination1",
        process_description="process_description1",
        channel_description="channel_description1",
    ),
    ChannelDesription(
        access="WRITE_ONLY",
        process="process2",
        channel="channel2",
        destination="destination2",
        process_description="process_description2",
        channel_description="channel_description2",
    ),
    app=FastAPI(
        title="1C ESB Gateway",
        description=(
            "Compatible server for 1C Enterprise ESB integration (OIDC + AMQP).\n"
            "Принимает уведомления по AMQP (из 1С) или HTTP POST."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        redirect_slashes=False,
        openapi_url="/openapi.json",
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
        debug=__debug__,
    ),
)


# ---------------------------------------------------------------------------
# POST / — альтернатива AMQP (для отладки / внешних систем)
# ---------------------------------------------------------------------------


@app.post("/", status_code=204, response_model=None)
async def post(
    payload: PayloadSchema,
    request: Request,
) -> None:
    """Принять уведомление для HTTP-доставки.

    **Формат тела** — JSON, соответствующий ``PayloadSchema``.

    **HTTP-режим:** отправьте POST на ``/`` с ``Content-Type: application/json``.
    Сервер сгенерирует ``message_id`` (UUIDv4) и создаст расписание доставки.

    **AMQP-режим (из 1С):** отправьте сообщение в очередь AMQP с routing key
    ``= destination``. Тело сообщения — тот же JSON, ``message_id`` берётся
    из свойств AMQP-сообщения (``properties.message_id``).

    **Процесс доставки:**
    1. Первая попытка POST на ``url`` — немедленно.
    2. При ошибке (сеть, таймаут, HTTP-статус >= 400) — повтор через ``pause`` секунд.
    3. Попытки продолжаются до истечения ``ttl`` секунд с момента получения.
    4. При успехе (HTTP 2xx) расписание удаляется — повторных попыток не будет.
    """
    from .delivery import create_delivery_schedule

    scheduler = request.app.state.scheduler
    message_id = str(uuid4())

    # ── trace_id: из тела запроса, либо из заголовка X-Trace-Id ──
    trace_id = resolve_trace_id(payload.trace_id, payload.headers)

    schedule_id = await create_delivery_schedule(
        scheduler,
        destination="http",
        url=str(payload.url),
        body=payload.body,
        headers=list(payload.headers) if payload.headers else None,
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        trace_id=trace_id,
        message_id=message_id,
    )

    PayloadReceivedEvent(
        message_id=message_id,
        destination="http",
        url=str(payload.url),
        headers=fmt_headers(payload.headers),
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        trace_id=trace_id,
        schedule_id=schedule_id,
    ).emit()


# ---------------------------------------------------------------------------
# GET /metrics — метрики доставки (in-memory)
# ---------------------------------------------------------------------------


@app.get("/metrics", status_code=200)
@app.get("/metrics/json", status_code=200)
async def get_metrics(request: Request) -> dict[str, object]:
    """Текущие метрики доставки сообщений.

    Счётчики сбрасываются при перезапуске процесса (in-memory).
    Поля: total_attempts, success_count, failure_count, avg_duration_ms.
    """
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is None:
        return {"status": "unavailable", "reason": "metrics not initialized"}
    return {"status": "ok", **metrics.stats}


# ---------------------------------------------------------------------------
# GET /health — health check (K8s liveness / readiness probe)
# ---------------------------------------------------------------------------


@app.get("/health", status_code=200)
@app.get("/health/live", status_code=200)
@app.get("/health/ready", status_code=200)
async def health(request: Request) -> dict[str, object]:
    """Health check — статус компонентов системы.

    Возвращает состояние scheduler'а, количество in-flight доставок,
    и uptime сервера.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    from app.delivery import _in_flight, _shutting_down

    return {
        "status": "ok",
        "scheduler": scheduler is not None,
        "in_flight": len(_in_flight),
        "shutting_down": _shutting_down,
    }
