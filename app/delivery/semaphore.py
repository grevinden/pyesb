"""Concurrency control — semaphore, in-flight tracking, shutdown guard."""

from __future__ import annotations

import asyncio

from app.config import settings
from app.events import (
    LogEvent,
    ShutdownCancelledEvent,
    ShutdownTimeoutEvent,
    ShutdownWaitingEvent,
)

__all__ = [
    "_delivery_semaphore",
    "_in_flight",
    "_shutting_down",
    "is_shutting_down",
    "set_shutting_down",
    "wait_for_in_flight",
]

# ── Concurrency control ───────────────────────────────────────────────
_delivery_semaphore: asyncio.Semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DELIVERIES)
"""Maximum concurrent HTTP deliveries (across all destinations)."""

# ── Shutdown guard ───────────────────────────────────────────────────
_in_flight: set[asyncio.Task] = set()
"""Множество asyncio.Task-ов, которые сейчас выполняют HTTP-запрос."""

_shutting_down: bool = False
"""Флаг: приложение выключается. Новые вызовы deliver_payload пропускаются."""


def set_shutting_down() -> None:
    """Set the shutdown flag — prevents new deliveries from starting.

    Must be a function (not direct assignment) because with ``from X import _shutting_down``
    followed by ``_shutting_down = True`` Python creates a **local** variable instead
    of mutating the module-level one.
    """
    global _shutting_down  # noqa: PLW0603
    _shutting_down = True


def is_shutting_down() -> bool:
    """Return current shutdown flag state.

    Use this instead of importing ``_shutting_down`` directly — since ``bool`` is
    immutable, ``from X import _shutting_down`` creates a copy and won't reflect
    later changes made via :func:`set_shutting_down`.
    """
    return _shutting_down


async def wait_for_in_flight(timeout: float | None = None) -> None:
    """Дождаться завершения всех in-flight доставок.

    Вызывается из shutdown-последовательности **до** того как
    APScheduler остановит свои task group-и.
    """
    if timeout is None:
        timeout = float(settings.SHUTDOWN_TIMEOUT)
    if not _in_flight:
        return
    ShutdownWaitingEvent(count=len(_in_flight), timeout=timeout).emit()
    done, pending = await asyncio.wait(_in_flight.copy(), timeout=timeout)
    if pending:
        ShutdownTimeoutEvent(remaining=len(pending), timeout=timeout).emit()
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        ShutdownCancelledEvent(count=len(pending)).emit()
    else:
        LogEvent().emit(event="shutdown_deliveries_completed")
