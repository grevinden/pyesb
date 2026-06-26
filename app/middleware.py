"""Middleware pipeline for the delivery chain.

Inspired by common middleware patterns in ASGI/WSGI frameworks.
Each middleware wraps the delivery call with ``before()`` and ``after()`` hooks::

    Before chain:  M1.before → M2.before → … → HTTP POST
    After chain:   … → M2.after → M1.after   (reverse order)

Usage::

    from app.middleware import MiddlewarePipeline, LoggingMiddleware

    pipeline = MiddlewarePipeline(middlewares=[LoggingMiddleware()])
    await pipeline.run(ctx, http_call)
"""

from __future__ import annotations

import abc
import time
from collections.abc import Awaitable, Callable
from typing import Any

__all__ = [
    "DeliveryContext",
    "MetricsMiddleware",
    "Middleware",
    "MiddlewarePipeline",
    "duration_buckets",
]

# Duration buckets for histogram (in milliseconds)
duration_buckets: list[int] = [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000]


class DeliveryContext:
    """Context object passed through the middleware chain.

    Populated before delivery, updated by middlewares and the HTTP call.
    """

    def __init__(
        self,
        *,
        message_id: str,
        destination: str,
        url: str,
        body: dict | list | None = None,
        headers: dict[str, str] | None = None,
        timeout: int,
        schedule_id: str,
        trace_id: str | None = None,
    ) -> None:
        self.message_id = message_id
        self.destination = destination
        self.url = url
        self.body = body
        self.headers = headers or {}
        self.timeout = timeout
        self.schedule_id = schedule_id
        self.trace_id = trace_id

        # Filled during delivery
        self.start_time: float = time.monotonic()
        self.duration_ms: int | None = None
        self.status_code: int | None = None
        self.response_body: str | None = None
        self.response_headers: dict[str, str] | None = None
        self.error: Exception | None = None


class Middleware(abc.ABC):
    """Base class for delivery middleware.

    Subclasses override ``before()`` and/or ``after()``.
    Both hooks are optional (no-op by default).
    """

    async def before(self, ctx: DeliveryContext) -> None:  # noqa: B027
        """Called before the HTTP POST. May modify ``ctx`` or raise."""

    async def after(self, ctx: DeliveryContext) -> None:  # noqa: B027
        """Called after the HTTP POST (success or failure).

        ``ctx.error`` is set if the call failed.
        """


class MiddlewarePipeline:
    """Chain of middlewares that wrap a delivery call.

    Middlewares are called in order for ``before()`` and in reverse
    order for ``after()``, forming an onion-like wrapper.
    """

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        self._middlewares = list(middlewares or [])

    def add(self, middleware: Middleware) -> None:
        """Append a middleware to the chain."""
        self._middlewares.append(middleware)

    async def run(
        self,
        ctx: DeliveryContext,
        call: Callable[[], Awaitable[Any]],
    ) -> None:
        """Execute the middleware chain around *call*.

        Args:
            ctx: The delivery context (shared across middlewares).
            call: The actual HTTP POST callable.

        Raises:
            Any exception from ``call`` after middlewares have processed it.
        """
        # Before chain (forward order)
        for m in self._middlewares:
            await m.before(ctx)

        # Actual call
        try:
            await call()
        except Exception as exc:
            ctx.error = exc
            raise
        finally:
            # After chain (reverse order — onion model)
            ctx.duration_ms = int((time.monotonic() - ctx.start_time) * 1000)
            for m in reversed(self._middlewares):
                await m.after(ctx)


# ═══════════════════════════════════════════════════════════════════════
# Built-in middlewares
# ═══════════════════════════════════════════════════════════════════════


class MetricsMiddleware(Middleware):
    """Collect in-memory delivery metrics.

    Access via ``MetricsMiddleware.stats``::

        metrics = MetricsMiddleware()
        pipeline = MiddlewarePipeline(middlewares=[metrics])
        ...
        print(metrics.stats)

    Values are reset on process restart (in-memory only).
    """

    def __init__(self) -> None:
        self.total_attempts: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.total_duration_ms: int = 0
        self._duration_buckets: list[int] = duration_buckets
        self._duration_histogram: dict[int, int] = {b: 0 for b in duration_buckets}

    @property
    def stats(self) -> dict[str, Any]:
        """Return current aggregated metrics."""
        return {
            "total_attempts": self.total_attempts,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": (
                self.total_duration_ms // self.total_attempts if self.total_attempts else 0
            ),
            "duration_histogram": self._duration_histogram.copy(),
        }

    async def before(self, ctx: DeliveryContext) -> None:
        self.total_attempts += 1

    async def after(self, ctx: DeliveryContext) -> None:
        if ctx.error is not None:
            self.failure_count += 1
        elif ctx.status_code is not None and 200 <= ctx.status_code < 300:
            self.success_count += 1
        else:
            self.failure_count += 1

        if ctx.duration_ms is not None:
            self.total_duration_ms += ctx.duration_ms
            for b in self._duration_buckets:
                if ctx.duration_ms <= b:
                    self._duration_histogram[b] += 1
                    break
