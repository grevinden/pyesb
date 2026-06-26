"""Pydantic models for the ESB Gateway.

PayloadSchema — уведомление для доставки на внешний URL.
Message — AMQP-сообщение, где body (JSON) парсится через Pydantic.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, Json, PositiveInt
from pyesb_amqp import E1CMessage

__all__ = [
    "Message",
    "PayloadSchema",
]


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
