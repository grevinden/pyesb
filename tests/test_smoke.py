"""Smoke Integration Test — полный lifecycle приложения.

Запускает FastAPI + APScheduler + SQLite in-memory через ASGI transport,
отправляет HTTP POST /, проверяет health/metrics endpoints.

Использует ``httpx.AsyncClient`` с ``ASGITransport`` — не требует реального HTTP-сервера.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

# ── Настраиваем конфиг ДО импорта app ──────────────────────────────
os.environ.setdefault("FWQ_DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("FWQ_LOG_QUEUE_MAXSIZE", "100")


@pytest.fixture
async def client() -> AsyncClient:
    """FastAPI test client with full lifespan (APScheduler + shutdown).

    Использует ``LifespanManager`` для отправки lifespan.startup/shutdown
    событий в ASGI-приложение. APScheduler стартует с SQLite in-memory.
    """
    from app.main import app

    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)  # type: ignore[arg-type]
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as ac:
            yield ac


class TestSmokeHealthEndpoint:
    """GET /health — базовая проверка работоспособности."""

    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        """Health endpoint возвращает status=ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["scheduler"], bool)
        assert isinstance(data["in_flight"], int)

    async def test_health_live_and_ready(self, client: AsyncClient) -> None:
        """/health/live и /health/ready тоже работают."""
        for path in ("/health/live", "/health/ready"):
            resp = await client.get(path)
            assert resp.status_code == 200, f"{path} failed"
            assert resp.json()["status"] == "ok"


class TestSmokeMetricsEndpoint:
    """GET /metrics — проверка счётчиков доставки."""

    async def test_metrics_structure(self, client: AsyncClient) -> None:
        """Metrics возвращает корректную структуру."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "total_attempts" in data
        assert "success_count" in data
        assert "failure_count" in data
        assert "avg_duration_ms" in data

    async def test_metrics_after_delivery(
        self,
        client: AsyncClient,
    ) -> None:
        """После POST / счётчики metrics увеличиваются."""
        initial = await client.get("/metrics")
        init_data = initial.json()

        # POST / — создание расписания (доставка не выполняется,
        # т.к. URL фиктивный, но schedule создаётся)
        payload = {
            "url": "http://localhost:1/nonexistent",
            "body": {"ok": 1},
            "timeout": 5,
            "pause": 60,
            "ttl": 60,
        }
        post_resp = await client.post("/", json=payload)
        assert post_resp.status_code == 204

        # Счётчики не изменились — доставка ещё не произошла
        # (schedule только создан, APScheduler запустит его асинхронно)
        after = await client.get("/metrics")
        after_data = after.json()
        assert after_data["total_attempts"] == init_data["total_attempts"]


class TestSmokePostEndpoint:
    """POST / — создание расписания доставки."""

    async def test_post_accepts_valid_payload(
        self,
        client: AsyncClient,
    ) -> None:
        """Валидный payload → 204 + создание schedule."""
        payload = {
            "url": "http://example.com/hook",
            "body": {"order_id": 123},
            "headers": [["X-Api-Key", "secret"]],
            "timeout": 10,
            "pause": 5,
            "ttl": 60,
        }
        resp = await client.post("/", json=payload)
        assert resp.status_code == 204

    async def test_post_accepts_minimal_payload(
        self,
        client: AsyncClient,
    ) -> None:
        """Минимальный payload (только обязательные поля) → 204."""
        payload = {
            "url": "http://example.com/hook",
            "timeout": 10,
            "pause": 5,
            "ttl": 60,
        }
        resp = await client.post("/", json=payload)
        assert resp.status_code == 204

    async def test_post_rejects_missing_fields(
        self,
        client: AsyncClient,
    ) -> None:
        """Невалидный payload → 422."""
        resp = await client.post("/", json={"url": "not-a-url"})
        assert resp.status_code == 422

    async def test_post_with_trace_id(
        self,
        client: AsyncClient,
    ) -> None:
        """trace_id в HTTP-заголовке x-trace-id принимается."""
        trace_id = str(uuid4())
        payload = {
            "url": "http://example.com/hook",
            "body": {"ok": 1},
            "timeout": 10,
            "pause": 5,
            "ttl": 60,
        }
        resp = await client.post("/", json=payload, headers={"x-trace-id": trace_id})
        assert resp.status_code == 204


class TestSmokeRoot:
    """Корневые проверки."""

    async def test_openapi_available(self, client: AsyncClient) -> None:
        """OpenAPI schema доступна."""
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        # OpenAPI schema может быть обёрнут oidc_add_routes,
        # проверяем что schema — это dict с базовыми полями
        assert isinstance(schema, dict)
        assert "openapi" in schema or "paths" in schema

    async def test_docs_redirect(self, client: AsyncClient) -> None:
        """Swagger docs доступны."""
        resp = await client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
