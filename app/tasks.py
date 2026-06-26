"""Safe asyncio task creation — no silent failures.

Usage::

    from app.tasks import safe_create_task

    task = safe_create_task(some_coro(), name="my_task")
    # task.exception() is still available for explicit error handling
    # The wrapped version logs any unhandled exception automatically.
"""

from __future__ import annotations

import asyncio

from app.events import UnhandledTaskErrorEvent


def safe_create_task(
    coro: asyncio.Future[object] | asyncio.Task[object],
    *,
    name: str | None = None,
) -> asyncio.Task[None]:
    """Create an asyncio task with automatic exception logging.

    Ensures no "silent" task failures — every unhandled exception is logged
    via ``UnhandledTaskErrorEvent`` immediately when the task fails.

    **Why this matters:**
    A bare ``asyncio.create_task(handler(message))`` that raises will produce
    a "task exception was never retrieved" warning only **when the task is
    garbage collected** — too late for diagnostics. This wrapper logs the
    exception eagerly and re-raises so the runtime still sees it.

    CancelledError is silently swallowed (expected during shutdown).

    Args:
        coro: The coroutine or awaitable to wrap.
        name: Optional task name (passed to ``asyncio.create_task``).

    Returns:
        The created asyncio.Task.
    """
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
