"""Async SQLite engine singleton — only for APScheduler's SQLAlchemyDataStore."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import settings

_engine: AsyncEngine | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Return (and create on first call) the global async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            db_url or settings.DATABASE_URL,
            echo=False,
        )
    return _engine


async def close_db() -> None:
    """Dispose the engine. Call once on FastAPI shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
