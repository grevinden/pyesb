"""1C ESB Gateway — FastAPI + APScheduler delivery + async SQLite.

Все события доставки пишутся в JSONL через structlog.
БД (``data.db``) содержит только APScheduler-таблицы — мелкая, не пухнет.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from uuid import uuid4

from apscheduler import AsyncScheduler, TaskDefaults
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, HttpUrl, Json, PositiveInt
from pyesb_amqp import AmqpMessage, AmqpServer, E1CMessage
from pyesb_amqp.oidc import ChannelDesription
from pyesb_amqp.oidc import add_routes as oidc_add_routes

from .database import close_db, get_engine
from .log import get_logger, load_logging_config, stderr_redirect_lifespan

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
    logger = get_logger("lifespan")
    logger.info("service_startup")

    from .delivery import create_delivery_schedule

    # Guard — захватывает logger из замыкания
    @asynccontextmanager
    async def _shutdown_guard() -> AsyncGenerator[None, None]:
        from .delivery import _shutting_down, wait_for_in_flight

        try:
            yield
        finally:
            _shutting_down = True
            logger.info("shutdown: amqp_stopped")
            await wait_for_in_flight(timeout=30)
            logger.info("shutdown: deliveries_resolved")

    async with AsyncExitStack() as exit_stack:
        # ── 1. Scheduler (exits LAST) ─────────────────────────────────
        scheduler = AsyncScheduler(
            data_store=SQLAlchemyDataStore(get_engine()),
            max_concurrent_jobs=20,
            task_defaults=TaskDefaults(max_running_jobs=None),
        )
        await exit_stack.enter_async_context(scheduler)
        await scheduler.start_in_background()
        logger.info("scheduler_started", max_concurrent=20)

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
                sender_code = parsed.application_properties.integ_sender_code
                recipient_code = parsed.application_properties.integ_recipient_code
                integ_message_id = str(parsed.application_properties.integ_message_id)

                schedule_id = await create_delivery_schedule(
                    scheduler,
                    destination=destination,
                    url=str(ps.url),
                    body=ps.body,
                    headers=list(ps.headers) if ps.headers else None,
                    timeout=ps.timeout,
                    pause=ps.pause,
                    ttl=ps.ttl,
                    message_id=message_id,
                )

                logger.info(
                    "payload_received",
                    message_id=message_id,
                    correlation_id=correlation_id,
                    sender_code=sender_code,
                    recipient_code=recipient_code,
                    integ_message_id=integ_message_id,
                    destination=destination,
                    url=str(ps.url),
                    headers=([list(h) for h in ps.headers] if ps.headers else None),
                    timeout=ps.timeout,
                    pause=ps.pause,
                    ttl=ps.ttl,
                    schedule_id=schedule_id,
                )
                return True
            except Exception as e:
                logger.error(
                    "handler_failed",
                    destination=destination,
                    error=f"{type(e).__name__}: {e}",
                )
                return False

        # ── 4. AMQP + stderr (exit FIRST) ─────────────────────────────
        await exit_stack.enter_async_context(stderr_redirect_lifespan())
        await exit_stack.enter_async_context(AmqpServer(handler=amqp_handler))

        # ── 5. Фиксируем scheduler в app.state ────────────────────────
        # Используем module-level app (oidc_add_routes wrapper),
        # т.к. request.app при обращении из эндпоинта — это враппер,
        # а не оригинальный FastAPI (_app).
        app.state.scheduler = scheduler  # noqa: F821 — module-level app
        yield

    # ── После выхода из стека: scheduler остановлен ────────────────────
    await close_db()
    logger.info("shutdown: complete")


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

    schedule_id = await create_delivery_schedule(
        scheduler,
        destination="http",
        url=str(payload.url),
        body=payload.body,
        headers=list(payload.headers) if payload.headers else None,
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        message_id=message_id,
    )

    logger = get_logger("http")
    logger.info(
        "payload_received",
        message_id=message_id,
        destination="http",
        url=str(payload.url),
        headers=([list(h) for h in payload.headers] if payload.headers else None),
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        schedule_id=schedule_id,
    )
