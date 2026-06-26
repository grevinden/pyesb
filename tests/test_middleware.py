"""Tests for safe task creation, middleware pipeline, and Semaphore control."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.delivery.middleware import (
    DeliveryContext,
    Middleware,
    MiddlewarePipeline,
)
from app.delivery.tasks import safe_create_task

# ═══════════════════════════════════════════════════════════════════════
# app.tasks — safe_create_task
# ═══════════════════════════════════════════════════════════════════════


class TestSafeCreateTask:
    """safe_create_task wraps exceptions, passes CancelledError through."""

    async def test_success(self) -> None:
        """Successful coroutine — no error."""
        sentinel: list[str] = []

        async def ok() -> None:
            sentinel.append("done")

        task = safe_create_task(ok(), name="test_ok")
        await task
        assert sentinel == ["done"]

    async def test_exception_is_logged_and_re_raised(self) -> None:
        """Exception is logged and re-raised (not silently swallowed)."""

        async def crash() -> None:
            msg = "intentional crash"
            raise ValueError(msg)

        with (
            patch("app.events.UnhandledTaskErrorEvent.emit") as mock_emit,
            pytest.raises(ValueError, match="intentional crash"),
        ):
            task = safe_create_task(crash(), name="test_crash")
            await task

        mock_emit.assert_called_once()

    async def test_cancelled_error_swallowed(self) -> None:
        """CancelledError is silently swallowed (expected during shutdown).

        safe_create_task catches CancelledError inside _wrapped() and lets
        the task complete normally — the awaiter does NOT see CancelledError.
        """
        event = asyncio.Event()

        async def will_be_cancelled() -> None:
            event.set()
            await asyncio.sleep(999)

        with patch("app.events.UnhandledTaskErrorEvent.emit") as mock_emit:
            task = safe_create_task(will_be_cancelled(), name="test_cancel")
            await event.wait()  # ensure coroutine is actually running
            task.cancel()
            await task  # safe_create_task swallows CancelledError
            # Should not log anything — CancelledError is expected
            mock_emit.assert_not_called()

    async def test_task_name_preserved(self) -> None:
        """Task name is passed through to asyncio.create_task."""

        async def my_coro() -> None:
            pass

        task = safe_create_task(my_coro(), name="custom_task_name")
        assert task.get_name() == "custom_task_name"
        await task


# ═══════════════════════════════════════════════════════════════════════
# app.middleware — MiddlewarePipeline
# ═══════════════════════════════════════════════════════════════════════


class TestMiddlewarePipeline:
    """MiddlewarePipeline calls before/after hooks in correct order."""

    async def test_empty_pipeline(self) -> None:
        """Empty pipeline calls the wrapped function without error."""
        pipeline = MiddlewarePipeline()
        called = False

        async def action() -> None:
            nonlocal called
            called = True

        ctx = DeliveryContext(
            message_id="m1",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="s1",
        )
        await pipeline.run(ctx, action)
        assert called

    async def test_before_and_after_order(self) -> None:
        """Middlewares are called forward for before, reverse for after."""
        order: list[str] = []

        class M1(Middleware):
            async def before(self, ctx: DeliveryContext) -> None:
                order.append("M1.before")

            async def after(self, ctx: DeliveryContext) -> None:
                order.append("M1.after")

        class M2(Middleware):
            async def before(self, ctx: DeliveryContext) -> None:
                order.append("M2.before")

            async def after(self, ctx: DeliveryContext) -> None:
                order.append("M2.after")

        pipeline = MiddlewarePipeline([M1(), M2()])

        async def action() -> None:
            order.append("action")

        ctx = DeliveryContext(
            message_id="m1",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="s1",
        )
        await pipeline.run(ctx, action)
        assert order == ["M1.before", "M2.before", "action", "M2.after", "M1.after"]

    async def test_exception_in_action(self) -> None:
        """After hooks are still called when action raises."""
        after_called: list[str] = []

        class TrackingMiddleware(Middleware):
            async def after(self, ctx: DeliveryContext) -> None:
                after_called.append("after")
                assert ctx.error is not None

        pipeline = MiddlewarePipeline([TrackingMiddleware()])

        async def failing_action() -> None:
            msg = "boom"
            raise ValueError(msg)

        ctx = DeliveryContext(
            message_id="m1",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="s1",
        )
        with pytest.raises(ValueError, match="boom"):
            await pipeline.run(ctx, failing_action)

        assert after_called == ["after"]
        assert isinstance(ctx.error, ValueError)

    async def test_context_populated(self) -> None:
        """DeliveryContext gets duration_ms, status_code, response data."""
        pipeline = MiddlewarePipeline()

        async def action() -> None:
            pass

        ctx = DeliveryContext(
            message_id="m1",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="s1",
        )
        ctx.status_code = 200
        ctx.response_body = '{"ok": true}'
        ctx.response_headers = {"content-type": "application/json"}

        await pipeline.run(ctx, action)

        assert ctx.duration_ms is not None
        assert ctx.duration_ms >= 0
        assert ctx.status_code == 200
        assert ctx.response_body == '{"ok": true}'

    async def test_middleware_added_dynamically(self) -> None:
        """Middleware can be added after construction."""
        order: list[str] = []

        class M1(Middleware):
            async def before(self, ctx: DeliveryContext) -> None:
                order.append("M1.before")

        pipeline = MiddlewarePipeline()
        pipeline.add(M1())

        async def action() -> None:
            order.append("action")

        ctx = DeliveryContext(
            message_id="m1",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="s1",
        )
        await pipeline.run(ctx, action)
        assert order == ["M1.before", "action"]
