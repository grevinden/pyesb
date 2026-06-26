"""Pydantic models for the ESB Gateway.

PayloadSchema — уведомление для доставки на внешний URL.
Message — AMQP-сообщение, где body (JSON) парсится через Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, HttpUrl, Json, PositiveInt
from pyesb_amqp import E1CMessage

__all__ = [
    "Message",
    "PayloadSchema",
]


class PayloadSchema(BaseModel):
    """Тело сообщения для доставки на внешний URL.

    Содержит только данные payload. Идентификатор трассировки
    ``trace_id`` передаётся в заголовке сообщения ``x-trace-id``
    (HTTP-заголовок или AMQP application property), а не в теле.

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

    body: Json[PayloadSchema]  # type: ignore[assignment]

    @property
    def payload(self) -> PayloadSchema:
        return self.body
