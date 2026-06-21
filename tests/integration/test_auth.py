"""Integration tests for OIDC authentication endpoint."""

import base64

import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.token import _ensure_keys


def test_token_endpoint_success():
    """Test successful token generation — any credentials are accepted."""
    client = TestClient(app)

    auth_header = f"Basic {base64.b64encode(b'test:test').decode('ascii')}"

    response = client.post(
        "/auth/oidc/token",
        headers={"Authorization": auth_header},
        data={"grant_type": "client_credentials"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "id_token" in data
    assert data["access_token"] == "Not implemented"
    assert data["token_type"] == "Bearer"

    # Verify JWT structure (basic validation)
    _, public_pem = _ensure_keys()
    payload = jwt.decode(
        data["id_token"],
        public_pem,
        algorithms=["RS512"],
        options={"verify_iss": False, "verify_sub": False, "verify_aud": False},
    )
    assert "sub" in payload
    assert "aud" in payload


def test_token_endpoint_no_auth_header():
    """Test token endpoint without authorization header — still works."""
    client = TestClient(app)

    response = client.post(
        "/auth/oidc/token",
        data={"grant_type": "client_credentials"},
    )

    # No auth check — should still succeed
    assert response.status_code == 200


def test_token_endpoint_invalid_grant_type():
    """Test token endpoint with invalid grant_type."""
    client = TestClient(app)

    response = client.post(
        "/auth/oidc/token",
        data={"grant_type": "password"},
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == 1
    assert error["status"] == "INVALID_REQUEST"
