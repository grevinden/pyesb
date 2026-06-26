"""Router — маршрутизация входящих сообщений и утилиты парсинга.

Выделен из ``main.py`` для соблюдения SRP: все функции, связанные
с определением маршрута сообщения (destination, trace_id, заголовки),
живут здесь.

В текущей версии роутинг простой:
* AMQP: destination приходит из routing key (устанавливается pyesb_amqp).
* HTTP: destination = ``"http"``.
* trace_id: из тела сообщения (приоритет) или заголовка ``X-Trace-Id``.
"""

from __future__ import annotations

from uuid import UUID

_TRACE_ID_HEADER = "X-Trace-Id"


def resolve_trace_id(
    trace_id: UUID | None,
    headers: set[tuple[str, str]] | None,
) -> str | None:
    """Получить trace_id из тела сообщения (приоритет) или из заголовка X-Trace-Id.

    Если ``trace_id`` передан в теле (``PayloadSchema.trace_id``) — используем его.
    Иначе ищем заголовок ``X-Trace-Id`` в ``headers`` (case-insensitive).
    Возвращаем только валидный UUID.
    """
    # 1. Из тела сообщения (PayloadSchema.trace_id)
    if trace_id is not None:
        return str(trace_id)

    # 2. Из заголовка X-Trace-Id
    if headers:
        for key, value in headers:
            if key.lower() == _TRACE_ID_HEADER.lower():
                try:
                    UUID(value)
                    return value
                except ValueError:
                    pass
                return None  # нашли X-Trace-Id, но не UUID — не используем

    return None


def first_str(val: str | list[str] | None) -> str | None:
    """Извлечь первую строку из значения, которое может быть str, list[str] или None.

    AMQP application properties из pyesb_amqp иногда приходят как ``list[str]``
    (напр. ``integ_sender_code``, ``integ_recipient_code``).
    """
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return val


# Публичный экспорт для удобства импорта
__all__ = [
    "first_str",
    "resolve_trace_id",
]
