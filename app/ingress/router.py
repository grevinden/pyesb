"""Router — маршрутизация входящих сообщений и утилиты парсинга.

Выделен из ``main.py`` для соблюдения SRP: все функции, связанные
с определением маршрута сообщения (destination, trace_id, заголовки),
живут здесь.
"""

from __future__ import annotations

from uuid import UUID


def resolve_trace_id(raw: str | None) -> str | None:
    """Проверить и вернуть trace_id из заголовка ``x-trace-id``."""
    if raw:
        try:
            UUID(raw)
            return raw
        except ValueError:
            pass
    return None


def first_str(val: str | list[str] | None) -> str | None:
    """Извлечь первую строку из значения, которое может быть str, list[str] или None."""
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return val


__all__ = [
    "first_str",
    "resolve_trace_id",
]
