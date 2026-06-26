"""Pydantic models for the ESB Gateway.

PayloadSchema — уведомление для доставки на внешний URL.
Message — AMQP-сообщение, где body (JSON) парсится через Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, Json, PositiveInt
from pyesb_amqp import E1CMessage

from app.config import settings
from app.delivery.headers import HeaderTuple

__all__ = [
    "Message",
    "PayloadSchema",
]


class PayloadSchema(BaseModel):
    """Уведомление для HTTP-доставки на внешний URL.

    Сервис принимает уведомление по HTTP POST (``/``) или через AMQP-очередь
    и **доставляет его на ``url``** в виде HTTP POST-запроса.

    ---

    **Цикл доставки:**

    1. Первая попытка — немедленно после получения.
    2. При ошибке (сеть, таймаут, HTTP-статус >= 400) повтор через ``pause`` секунд.
    3. Попытки продолжаются до истечения ``ttl`` с момента получения.
    4. При успехе (HTTP 2xx) расписание удаляется, повторных попыток не будет.
    5. При исчерпании ``ttl`` сообщение попадает в Dead Letter Queue (DLQ).

    **Трассировка:**

    Идентификатор ``trace_id`` передаётся **вне тела** —
    через HTTP-заголовок ``X-Trace-Id`` (для HTTP POST /)
    или AMQP application property (для AMQP-сообщений).
    """

    url: HttpUrl = Field(
        description="Адрес внешнего сервера. Уведомление будет отправлено"
        " как HTTP POST на этот URL с Content-Type: application/json.",
    )
    body: dict | list | None = Field(
        default=None,
        description="Тело запроса. Произвольный JSON-объект или массив,"
        " который будет передан в POST-запросе на `url` как есть."
        " Поддерживается любой вложенный JSON без ограничений по схеме.",
    )
    headers: set[HeaderTuple] | None = Field(
        default=None,
        description="Дополнительные HTTP-заголовки запроса."
        ' Каждый элемент — пара `["Header-Name", "value"]`.'
        ' Например: `[["Authorization", "Bearer token"], ["X-Custom", "val"]]`.'
        " Заголовки объединяются с системными (`Content-Type`, `Host` и т.д.).",
    )
    timeout: PositiveInt = Field(
        description="Таймаут ожидания ответа от внешнего сервера (секунды)."
        " Если сервер не ответил за это время — попытка считается неудачной.",
        le=settings.MAX_TIMEOUT,
    )
    pause: PositiveInt = Field(
        description="Пауза между повторными попытками (секунды)."
        " После каждой неудачной попытки сервис ждёт ``pause`` секунд"
        " перед следующим запросом. Например: ``pause=10`` → повтор каждые 10 секунд.",
        le=settings.MAX_PAUSE,
    )
    ttl: PositiveInt = Field(
        description="Максимальное время жизни сообщения (секунды) с момента получения."
        " Если за это время сервер ни разу не ответил 2xx — "
        " доставка прекращается, сообщение уходит в DLQ."
        " Например: ``ttl=300`` → сообщение будет доставляться максимум 5 минут.",
        le=settings.MAX_TTL,
    )


class Message(E1CMessage):
    """AMQP-сообщение, где body (JSON) парсится через Pydantic."""

    body: Json[PayloadSchema]  # type: ignore[assignment]

    @property
    def payload(self) -> PayloadSchema:
        return self.body
