"""Shared context variables — used by delivery engine.

Вынесены в отдельный модуль, чтобы избежать циклического импорта.
"""

from __future__ import annotations

import contextvars

__all__ = [
    "message_id_var",
    "trace_id_var",
]

message_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "message_id", default=None
)
"""UUIDv4 сообщения. Автоматически inject во все логи внутри доставки."""

trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
"""UUID сквозной трассировки. Автоматически inject во все логи внутри доставки."""
