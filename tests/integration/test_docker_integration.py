"""Integration tests that run against the Docker container."""

import base64
import time

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint via HTTP."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://app:9090/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_token_endpoint_docker():
    """Test token endpoint via HTTP against Docker container."""
    async with httpx.AsyncClient() as client:
        # Wait a bit for the service to be fully ready
        time.sleep(2)

        auth_header = f"Basic {base64.b64encode(b'test:test').decode('ascii')}"
        response = await client.post(
            "http://app:9090/auth/oidc/token",
            headers={"Authorization": auth_header},
            data={"grant_type": "client_credentials"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "id_token" in data
        assert data["access_token"] == "Not implemented"
        assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_metadata_endpoint_docker():
    """Test metadata endpoint via HTTP against Docker container."""
    async with httpx.AsyncClient() as client:
        # Get token first
        auth_header = f"Basic {base64.b64encode(b'test:test').decode('ascii')}"
        token_response = await client.post(
            "http://app:9090/auth/oidc/token",
            headers={"Authorization": auth_header},
            data={"grant_type": "client_credentials"},
        )
        assert token_response.status_code == 200
        id_token = token_response.json()["id_token"]

        # Test metadata endpoint
        response = await client.get(
            "http://app:9090/applications/test/sys/esb/metadata/channels",
            headers={"Authorization": f"Bearer {id_token}"},
        )

        assert response.status_code == 200
        channels = response.json()
        assert isinstance(channels, list)
        assert len(channels) > 0

        # Verify channel structure
        for channel in channels:
            assert "process" in channel
            assert "channel" in channel
            assert "access" in channel
