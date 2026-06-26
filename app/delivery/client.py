"""Shared httpx client with circuit breaker per URL."""

from __future__ import annotations

import httpx
from cashews import cache

from app.config import settings

__all__ = [
    "_get_http_client",
    "_http_post_with_cb",
    "close_http_client",
]


@cache.circuit_breaker(
    errors_rate=10,
    period="1m",
    ttl="5m",
    half_open_ttl="1m",
    key="{url}",
)
async def _http_post_with_cb(
    client: httpx.AsyncClient,
    url: str,
    headers_dict: dict[str, str],
    body: dict | list | None,
    timeout: int,
) -> httpx.Response:
    """HTTP POST с circuit breaker per URL.

    Если за последнюю минуту на этот URL было >=10 ошибок,
    circuit breaker размыкается на 5 минут ("open").
    """
    return await client.post(url, json=body, headers=headers_dict, timeout=timeout)


# ── Shared httpx client ──────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, creating it if needed."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=settings.MAX_CONCURRENT_DELIVERIES,
                max_keepalive_connections=settings.MAX_CONCURRENT_DELIVERIES,
            ),
            verify=False,  # Требование заказчика: отключить проверку SSL
        )
    return _http_client


async def close_http_client() -> None:
    """Close the shared httpx.AsyncClient."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
