"""``app.config`` — consolidated configuration and bootstrap for pyesb-webhooker.

Everything related to application configuration lives here:
environment variables, database engine, logging config, and the startup
bootstrap sequence.

Usage::

    from app.config import settings
    from app.config import bootstrap
    from app.config import get_engine, close_db, setup_db

See individual submodules for details.
"""

from __future__ import annotations

from ._bootstrap import bootstrap
from ._database import close_db, get_engine, setup_db
from ._settings import Settings, settings

__all__ = [
    "Settings",
    "bootstrap",
    "close_db",
    "get_engine",
    "settings",
    "setup_db",
]
