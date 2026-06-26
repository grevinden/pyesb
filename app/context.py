"""Shared context variables — used by ``delivery.py`` and ``log.py``.

Вынесены в отдельный модуль, чтобы избежать циклического импорта
между ``app.delivery`` и ``app.log``::

    delivery.py  ──imports──▶  structlog (runtime)  ──processor──▶  log.py
    log.py       ──imports──▶  context.py (вместо delivery.py)

``message_id_var`` и ``trace_id_var`` устанавливаются в ``deliver_payload``,
читаются из ``log._add_context_vars``.
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
"""UUIDv4 сообщения. Автоматически inject во все structlog-логи внутри доставки."""

trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
"""UUID сквозной трассировки. Автоматически inject во все structlog-логи внутри доставки."""
