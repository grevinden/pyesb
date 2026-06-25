"""1C ESB Gateway — FastAPI + async SQLite + Active Record."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl, Json, PositiveInt
from pyesb_amqp import AmqpMessage, AmqpServer, E1CMessage
from pyesb_amqp.oidc import ChannelDesription
from pyesb_amqp.oidc import add_routes as oidc_add_routes
from sqlalchemy import String
from sqlmodel import Field

from .database import AutoRecord, close_db, init_db
from .log import get_logger, load_logging_config, stderr_redirect_lifespan
from .types import DillPickle


class PayloadSchema(BaseModel):
    """Pydantic-схема для валидации JSON из AMQP body.

    SQLModel ``Payload`` не валидирует поля при создании
    (``__init__`` от SQLAlchemy проставляет None для отсутствующих ключей).
    Эта схема используется для строгой валидации **до** сохранения.
    """

    url: HttpUrl
    body: dict | list | None = None
    headers: set[tuple[str, str]] | None = None
    timeout: PositiveInt
    pause: PositiveInt
    count: PositiveInt


class Message(E1CMessage):
    """AMQP-сообщение, где body (JSON) парсится через Pydantic-схему."""

    class Payload(AutoRecord, table=True):
        __tablename__: str = "payloads"  # type: ignore[assignment]

        id: PositiveInt = Field(primary_key=True)
        destination: str
        url: HttpUrl = Field(sa_type=String)
        body: dict | list | None = Field(sa_type=DillPickle)
        headers: set[tuple[str, str]] | None = Field(sa_type=DillPickle)
        timeout: PositiveInt
        pause: PositiveInt
        count: PositiveInt

    payload: Json[PayloadSchema] = Field(validation_alias="body")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[dict, None]:
    """Start and stop the AMQP server alongside FastAPI."""

    load_logging_config()
    logger = get_logger("lifespan")

    await init_db()

    async def amqp_handler(destination: str, msg: AmqpMessage) -> bool:
        try:
            # 1. Pydantic-валидация JSON из AMQP body
            parsed = Message.model_validate(
                msg, from_attributes=True, context={"destination": destination}
            )
            ps = parsed.payload  # PayloadSchema — уже проверен Pydantic

            # 2. Создаём SQLModel-запись для сохранения.
            # id не передаём — SQLAlchemy auto-generates; type checker
            # может ругаться на отсутствие id, это нормально.
            record = Message.Payload(  # type: ignore[call-arg]
                destination=destination,
                url=str(ps.url),
                body=ps.body,
                headers=ps.headers,
                timeout=ps.timeout,
                pause=ps.pause,
                count=ps.count,
            )
            await record.save()
            logger.info(
                "payload_saved",
                destination=destination,
                payload_id=record.id,
            )
            return True
        except Exception as e:
            logger.error(
                "payload_save_failed",
                destination=destination,
                error=str(e),
            )
            return False

    async with stderr_redirect_lifespan():
        async with AmqpServer(handler=amqp_handler):
            yield {}

    await close_db()


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
        description="Compatible server for 1C Enterprise ESB integration (OIDC + AMQP)",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        redirect_slashes=False,
        openapi_url=None,
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
    ),
)
