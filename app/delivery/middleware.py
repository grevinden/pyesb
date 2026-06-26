"""Middleware pipeline for the delivery chain.

Inspired by common middleware patterns in ASGI/WSGI frameworks.
Each middleware wraps the delivery call with ``before()`` and ``after()`` hooks::

    Before chain:  M1.before → M2.before → … → HTTP POST
    After chain:   … → M2.after → M1.after   (reverse order)
"""

from __future__ import annotations

import abc
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .headers import validate_header_dict

__all__ = [
    "DeliveryContext",
    "Middleware",
    "MiddlewarePipeline",
]


class DeliveryContext:
    """Context object passed through the middleware chain."""

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

        # ── Валидация заголовков (CRLF injection prevention) ─────────
        if headers is not None:
            headers = validate_header_dict(headers)
        self.headers = headers or {}

        self.timeout = timeout
        self.schedule_id = schedule_id
        self.trace_id = trace_id

        self.start_time: float = time.monotonic()
        self.duration_ms: int | None = None
        self.status_code: int | None = None
        self.response_body: str | None = None
        self.response_headers: dict[str, str] | None = None
        self.error: Exception | None = None


class Middleware(abc.ABC):
    """Base class for delivery middleware."""

    async def before(self, ctx: DeliveryContext) -> None:  # noqa: B027
        """Called before the HTTP POST. May modify ``ctx`` or raise."""

    async def after(self, ctx: DeliveryContext) -> None:  # noqa: B027
        """Called after the HTTP POST (success or failure)."""


class MiddlewarePipeline:
    """Chain of middlewares that wrap a delivery call."""

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
        """Execute the middleware chain around *call*."""
        for m in self._middlewares:
            await m.before(ctx)

        try:
            await call()
        except Exception as exc:
            ctx.error = exc
            raise
        finally:
            ctx.duration_ms = int((time.monotonic() - ctx.start_time) * 1000)
            for m in reversed(self._middlewares):
                await m.after(ctx)
