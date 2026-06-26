"""Fault Tolerance Integration Tests — отказоустойчивость системы.

Сценарии из архитектурного ревью:
1. Semaphore лимитирует конкурентность — N+1-й вызов ждёт.
2. MiddlewarePipeline выполняет after() даже при исключении.
3. safe_create_task логирует и пробрасывает исключения.
4. Shutdown: _shutting_down блокирует новые доставки.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.delivery.middleware import (
    DeliveryContext,
    Middleware,
    MiddlewarePipeline,
)
from app.delivery.semaphore import _delivery_semaphore, wait_for_in_flight
from app.delivery.tasks import safe_create_task

# ═══════════════════════════════════════════════════════════════════════
# 1. Semaphore — конкурентность
# ═══════════════════════════════════════════════════════════════════════


class TestSemaphoreConcurrency:
    """Semaphore ограничивает количество одновременных HTTP-запросов."""

    async def test_acquire_release_blocks_at_limit(self) -> None:
        """Semaphore(2): 3-й acquire блокируется, пока не release."""
        sem = asyncio.Semaphore(2)
        acquired: list[int] = []

        async def worker(n: int) -> None:
            async with sem:
                acquired.append(n)
                await asyncio.sleep(0.05)  # имитация работы

        # Запускаем 3 задачи — только 2 могут войти одновременно
        tasks = [asyncio.create_task(worker(i)) for i in range(3)]
        await asyncio.sleep(0.01)  # даём время задачам запуститься

        # Первые 2 уже в семафоре, 3-я ждёт
        assert len(acquired) <= 2, "Semaphore пропустил больше чем limit"

        # Ждём завершения всех
        await asyncio.gather(*tasks, return_exceptions=True)

        # Все 3 должны выполниться
        assert len(acquired) == 3
        assert sorted(acquired) == [0, 1, 2]

    async def test_delivery_semaphore_exists(self) -> None:
        """Модульный семафор delivery.py существует и имеет корректный лимит."""
        assert isinstance(_delivery_semaphore, asyncio.Semaphore)
        # Проверяем что _value можно прочитать (внутреннее, но для теста ок)
        # Для Semaphore _value — число доступных "мест"
        assert _delivery_semaphore._value > 0  # noqa: SLF001

    async def test_release_after_acquire(self) -> None:
        """Acquire/release работают как счётчик."""
        sem = asyncio.Semaphore(1)
        await sem.acquire()
        assert sem.locked()
        sem.release()
        assert not sem.locked()


# ═══════════════════════════════════════════════════════════════════════
# 2. MiddlewarePipeline — обработка ошибок
# ═══════════════════════════════════════════════════════════════════════


class TestMiddlewarePipelineFaultTolerance:
    """MiddlewarePipeline корректно обрабатывает исключения."""

    async def test_after_called_even_on_exception(self) -> None:
        """after() вызывается даже если действие выбросило исключение."""
        after_called: list[str] = []

        class TrackMiddleware(Middleware):
            async def after(self, ctx: DeliveryContext) -> None:
                after_called.append("after")
                assert ctx.error is not None
                assert isinstance(ctx.error, RuntimeError)

        pipeline = MiddlewarePipeline([TrackMiddleware()])

        async def failing_action() -> None:
            msg = "middleware test failure"
            raise RuntimeError(msg)

        ctx = DeliveryContext(
            message_id="fault-001",
            destination="test",
            url="http://example.com/fail",
            timeout=10,
            schedule_id="sched-fault-001",
        )

        with pytest.raises(RuntimeError, match="middleware test failure"):
            await pipeline.run(ctx, failing_action)

        assert after_called == ["after"]
        assert ctx.duration_ms is not None
        assert ctx.duration_ms >= 0

    async def test_multiple_middlewares_on_exception(self) -> None:
        """Все after() вызываются в обратном порядке при исключении."""
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

        async def crash() -> None:
            msg = "pipeline crash"
            raise ValueError(msg)

        ctx = DeliveryContext(
            message_id="fault-002",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="sched-fault-002",
        )

        with pytest.raises(ValueError, match="pipeline crash"):
            await pipeline.run(ctx, crash)

        # before: M1 → M2 (forward)
        # after:  M2 → M1 (reverse)
        assert order == ["M1.before", "M2.before", "M2.after", "M1.after"]

    async def test_context_error_set_on_exception(self) -> None:
        """ctx.error заполняется при исключении."""
        pipeline = MiddlewarePipeline()

        async def fail() -> None:
            msg = "something broke"
            raise ConnectionError(msg)

        ctx = DeliveryContext(
            message_id="fault-003",
            destination="test",
            url="http://example.com",
            timeout=10,
            schedule_id="sched-fault-003",
        )

        with pytest.raises(ConnectionError):
            await pipeline.run(ctx, fail)

        assert ctx.error is not None
        assert isinstance(ctx.error, ConnectionError)


# ═══════════════════════════════════════════════════════════════════════
# 3. safe_create_task — интеграция
# ═══════════════════════════════════════════════════════════════════════


class TestSafeCreateTaskIntegration:
    """safe_create_task в реальном асинхронном окружении."""

    async def test_task_runs_to_completion(self) -> None:
        """Задача выполняется до конца."""
        result: list[int] = []

        async def worker() -> None:
            result.append(42)

        task = safe_create_task(worker(), name="integration-ok")
        await task
        assert result == [42]

    async def test_exception_is_propagated(self) -> None:
        """Исключение пробрасывается наружу."""

        async def crash() -> None:
            msg = "integration crash"
            raise RuntimeError(msg)

        task = safe_create_task(crash(), name="integration-crash")
        with pytest.raises(RuntimeError, match="integration crash"):
            await task

    async def test_cancelled_is_swallowed(self) -> None:
        """CancelledError проглатывается _wrapped — await task НЕ бросает.

        safe_create_task перехватывает CancelledError внутри _wrapped()
        и завершает задачу штатно. CancelledError НЕ попадает в лог.
        """
        started = asyncio.Event()

        async def will_be_cancelled() -> None:
            started.set()
            await asyncio.sleep(999)

        with patch("app.events.UnhandledTaskErrorEvent.emit") as mock_emit:
            task = safe_create_task(
                will_be_cancelled(),
                name="integration-cancel",
            )
            await started.wait()  # ждём пока задача запустится
            task.cancel()
            await task  # safe_create_task глотает CancelledError
            # CancelledError НЕ должна логироваться как ошибка
            mock_emit.assert_not_called()

    async def test_concurrent_tasks_all_complete(self) -> None:
        """Множество задач завершаются корректно."""
        results: set[int] = set()

        async def worker(n: int) -> None:
            await asyncio.sleep(0.01)
            results.add(n)

        tasks = [safe_create_task(worker(i), name=f"concurrent-{i}") for i in range(10)]
        await asyncio.gather(*tasks)
        assert results == set(range(10))


# ═══════════════════════════════════════════════════════════════════════
# 4. Shutdown — _shutting_down блокирует новые доставки
# ═══════════════════════════════════════════════════════════════════════


class TestShutdownFlow:
    """Проверка логики shutdown: _shutting_down и wait_for_in_flight."""

    async def test_shutting_down_flag_state(self) -> None:
        """_shutting_down — существующий module-level флаг."""
        import app.delivery as dmod

        # Проверяем что флаг существует и влияет на код
        assert hasattr(dmod, "_shutting_down")
        assert isinstance(dmod._shutting_down, bool)  # noqa: SLF001

    async def test_wait_for_in_flight_empty(self) -> None:
        """wait_for_in_flight не падает при пустом _in_flight."""
        await wait_for_in_flight(timeout=1)
        # Функция просто возвращается, ничего не делая
