"""``app.config._settings`` — единственный источник truth для всех параметров.

Все hardcoded значения вынесены в переменные окружения (префикс ``FWQ_``).
Использование::

    from app.config import settings

    sem = asyncio.Semaphore(settings.MAX_CONCURRENT_DELIVERIES)

Settings — frozen dataclass, создаётся при первом импорте.
Environment variables читаются ОДИН раз при старте процесса.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable settings — читаются из env при старте."""

    # ── Server ─────────────────────────────────────────────────────────
    BIND_HOST: str = os.getenv("FWQ_BIND_HOST", "0.0.0.0")
    BIND_PORT: int = int(os.getenv("FWQ_BIND_PORT", "8000"))

    # ── Concurrency ────────────────────────────────────────────────────
    MAX_CONCURRENT_DELIVERIES: int = int(os.getenv("FWQ_MAX_CONCURRENT_DELIVERIES", "50"))
    """Semaphore limit — одновременные HTTP-доставки."""

    SCHEDULER_MAX_CONCURRENT: int = int(os.getenv("FWQ_SCHEDULER_MAX_CONCURRENT", "20"))
    """APScheduler max_concurrent_jobs."""

    # ── Shutdown ───────────────────────────────────────────────────────
    SHUTDOWN_TIMEOUT: int = int(os.getenv("FWQ_SHUTDOWN_TIMEOUT", "30"))
    """Секунд ожидания in-flight доставок при shutdown."""

    # ── Logging ────────────────────────────────────────────────────────
    LOG_QUEUE_MAXSIZE: int = int(os.getenv("FWQ_LOG_QUEUE_MAXSIZE", "5000"))
    """Максимум записей в очереди QueueHandler."""

    # ── Database ───────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("FWQ_DATABASE_URL", "sqlite+aiosqlite:///data.db")
    """Async SQLAlchemy DSN для APScheduler."""

    # ── Delivery defaults ──────────────────────────────────────────────
    DEFAULT_PAUSE: int = int(os.getenv("FWQ_DEFAULT_PAUSE", "10"))
    """Пауза между retry по умолчанию (сек)."""

    DEFAULT_TTL: int = int(os.getenv("FWQ_DEFAULT_TTL", "300"))
    """TTL доставки по умолчанию (сек)."""

    DEFAULT_TIMEOUT: int = int(os.getenv("FWQ_DEFAULT_TIMEOUT", "30"))
    """HTTP-таймаут по умолчанию (сек)."""

    # ── Logging limits ───────────────────────────────────────────────────
    LOG_BODY_MAX_CHARS: int = int(os.getenv("FWQ_LOG_BODY_MAX_CHARS", "4096"))
    """Максимальная длина тела запроса в логах (символов)."""

    LOG_RESPONSE_BODY_MAX_CHARS: int = int(os.getenv("FWQ_LOG_RESPONSE_BODY_MAX_CHARS", "4096"))
    """Максимальная длина тела ответа в логах (символов)."""

    # ── Pretty print ───────────────────────────────────────────────────
    PRETTY_LOG: bool = os.getenv("FWQ_PRETTY_LOG", "").lower() in ("1", "true", "yes")
    """Форматированный вывод логов (indent=2) для разработки."""

    # ── Metrics ──────────────────────────────────────────────────────────
    DURATION_BUCKETS_MS: tuple[int, ...] = (10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000)
    """Границы гистограммы длительности доставки (мс)."""


# Module-level singleton (import once → frozen dataclass)
settings = Settings()

__all__ = ["Settings", "settings"]
