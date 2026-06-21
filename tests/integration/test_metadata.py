"""Integration tests for metadata endpoint."""

import base64

from fastapi.testclient import TestClient

from app.main import app


def test_channels_endpoint_success():
    """Test successful channel metadata retrieval."""
    client = TestClient(app)

    # Get valid token first
    auth_header = f"Basic {base64.b64encode(b'test:test').decode('ascii')}"
    token_response = client.post(
        "/auth/oidc/token",
        headers={"Authorization": auth_header},
        data={"grant_type": "client_credentials"},
    )
    assert token_response.status_code == 200
    id_token = token_response.json()["id_token"]

    # Test metadata endpoint
    response = client.get(
        "/applications/test/sys/esb/metadata/channels",
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
        assert channel["access"] in ["READ_ONLY", "WRITE_ONLY"]


def test_channels_endpoint_invalid_token():
    """Test metadata endpoint with invalid token."""
    client = TestClient(app)

    response = client.get(
        "/applications/test/sys/esb/metadata/channels",
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == 16
    assert error["status"] == "UNAUTHENTICATED"


def test_channels_endpoint_missing_token():
    """Test metadata endpoint without authorization header."""
    client = TestClient(app)

    response = client.get("/applications/test/sys/esb/metadata/channels")

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == 16
    assert error["status"] == "UNAUTHENTICATED"


def test_channels_endpoint_unknown_app():
    """Test metadata endpoint with unknown application."""
    client = TestClient(app)

    # Get valid token first
    auth_header = f"Basic {base64.b64encode(b'test:test').decode('ascii')}"
    token_response = client.post(
        "/auth/oidc/token",
        headers={"Authorization": auth_header},
        data={"grant_type": "client_credentials"},
    )
    assert token_response.status_code == 200
    id_token = token_response.json()["id_token"]

    # Test with unknown app
    response = client.get(
        "/applications/unknown/sys/esb/metadata/channels",
        headers={"Authorization": f"Bearer {id_token}"},
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == 5
    assert error["status"] == "NOT_FOUND"
