"""``app.config._bootstrap`` — единая точка инициализации приложения.

Вызывается ОДИН раз при старте (из lifespan). Порядок важен:

1. **Logging** — первым делом, чтобы все последующие логи попали в JSONL.
2. **Cache** — circuit breaker (cashews), до любого HTTP-вызова.
3. **Database** — PRAGMAs на engine singleton.

Использование::

    from app.config import bootstrap

    async with lifespan(app):
        bootstrap()
        ...
"""

from __future__ import annotations

import logging as _logging
from logging.config import dictConfig
from pathlib import Path

import yaml

__all__ = [
    "bootstrap",
    "init_cache",
    "init_logging",
]

# ═══════════════════════════════════════════════════════════════════════
# Public bootstrap
# ═══════════════════════════════════════════════════════════════════════


def bootstrap() -> None:
    """Initialize all application subsystems.

    Call order:

    1. :func:`init_logging` — JSONL-лог в stdout.
    2. :func:`init_cache` — in-memory cache + circuit breaker.
    """
    init_logging()
    init_cache()


# ═══════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════


def init_logging() -> None:
    """Configure stdlib logging via ``logging.{dev,pro}.yaml``.

    Выбор файла зависит от ``__debug__``:

    * ``__debug__ = True``  → ``logging.dev.yaml``  (local dev, отладка)
    * ``__debug__ = False`` → ``logging.pro.yaml``  (production, ``PYTHONOPTIMIZE=2``)

    Файлы лежат рядом с модулем (``app/config/logging.*.yaml``).

    All events go through Pydantic models (``.emit()``).
    Stdlib logs go through ``JsonlFormatter`` + ``logging.StreamHandler``.
    """
    if _logging.getLogger().hasHandlers():
        return

    _suffix = "dev" if __debug__ else "pro"
    _cfg_path = Path(__file__).resolve().parent / f"logging.{_suffix}.yaml"
    with _cfg_path.open() as _f:
        _cfg = yaml.safe_load(_f)
    dictConfig(_cfg)


# ═══════════════════════════════════════════════════════════════════════
# Cache / Circuit breaker
# ═══════════════════════════════════════════════════════════════════════


def init_cache() -> None:
    """Configure in-memory cache for cashews circuit breaker.

    In-memory circuit breaker для защиты целевых серверов от повторяющихся
    ошибок. Не требует Redis — in-memory достаточно для защиты от лавины.
    """
    from cashews import cache  # noqa: PLC0415 — lazy import, библиотека не всегда нужна

    cache.setup("mem://")
