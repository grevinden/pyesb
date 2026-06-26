"""JsonlFormatter — stdlib logging → JSONL через Pydantic-модели."""

from __future__ import annotations

import logging


class JsonlFormatter(logging.Formatter):
    """Stdlib log formatter that renders records as JSONL.

    Используется из ``logging.yaml`` через ``() : app.events.JsonlFormatter``.
    Каждая запись проходит через Pydantic-модель ``LogEvent`` напрямую.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json as _json_mod
        from datetime import datetime, timezone

        from app.events import LogEvent

        message = record.getMessage()
        now = datetime.fromtimestamp(record.created, tz=timezone.utc)

        # model_construct — без Pydantic-валидации, чтобы PastDatetime не падал
        # при точных таймингах (race condition между генерацией dt и now)
        event = LogEvent.model_construct()

        data = event.model_dump(mode="json", exclude_none=True)
        data["level"] = record.levelname.lower()
        data["event"] = message
        data["model"] = type(event).__name__
        data["logger"] = record.name
        data["timestamp"] = now.isoformat()

        from app.config import settings

        indent = 2 if settings.PRETTY_LOG else None
        return _json_mod.dumps(data, default=str, indent=indent)
