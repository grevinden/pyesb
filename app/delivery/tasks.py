"""Safe asyncio task creation — no silent failures.

Usage::

    from app.delivery.tasks import safe_create_task

    task = safe_create_task(some_coro(), name="my_task")
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.events import UnhandledTaskErrorEvent

__all__ = [
    "safe_create_task",
]


def safe_create_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
) -> asyncio.Task[None]:
    """Create an asyncio task with automatic exception logging."""
    task_name = name or getattr(coro, "__name__", None)

    async def _wrapped() -> None:
        try:
            await coro
        except asyncio.CancelledError:
            pass  # expected during shutdown
        except Exception:
            UnhandledTaskErrorEvent(task_name=task_name).emit()
            raise

    task = asyncio.create_task(_wrapped(), name=task_name)
    return task
