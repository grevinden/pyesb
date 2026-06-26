"""Async SQLite engine singleton — only for APScheduler's SQLAlchemyDataStore.

WAL mode and busy timeout are set automatically on every new connection
via SQLAlchemy's ``@event.listens_for``. This works correctly for both
file-based (``data.db``) and in-memory (``:memory:``) databases.

**Important:** ``poolclass`` is **not** set to ``NullPool`` because
in-memory SQLite requires connection reuse — each connection to
``:memory:`` creates a separate database. The default pool
(``AsyncAdaptedQueuePool``) is used.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import settings

__all__ = [
    "close_db",
    "get_engine",
    "setup_db",
]

_engine: AsyncEngine | None = None


def _set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
    """Set SQLite PRAGMAs on every new connection (WAL + busy timeout).

    Вызывается для каждого нового соединения. ``dbapi_connection`` —
    это синхронный ``sqlite3.Connection`` (не aiosqlite wrapper),
    поэтому ``cursor.execute`` работает синхронно.
    """
    cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=wal")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Return (and create on first call) the global async engine.

    Использует стандартный пул соединений (не ``NullPool``), чтобы
    in-memory SQLite работал корректно — все соединения разделяют
    одну базу данных.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            db_url or settings.DATABASE_URL,
            echo=False,
            connect_args={
                "check_same_thread": False,
            },
        )
        # Устанавливаем PRAGMAs на каждое новое соединение.
        # Слушаем только наш sync_engine, а не все Engine глобально.
        event.listen(_engine.sync_engine, "connect", _set_sqlite_pragmas)
    return _engine


async def close_db() -> None:
    """Dispose the engine. Call once on FastAPI shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def setup_db() -> None:
    """Enable WAL mode for SQLite. Call once on startup.

    **Note:** PRAGMAs are now set automatically by ``@event.listens_for``
    on every new connection. This function is kept for backward
    compatibility and for explicit calls in tests — currently a no-op.
    """
