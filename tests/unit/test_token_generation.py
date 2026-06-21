"""Unit tests for JWT token generation."""

import time

from app.config import AppConfig, ClientCredentials
from app.token import create_id_token, verify_id_token


def test_create_id_token_structure():
    """Test that created tokens have the correct structure."""
    client = ClientCredentials(
        client_id="test",
        client_secret="test",
        user_id="22af67ef-d0bd-4861-a7ed-519068ee7d68",
        user_list_id="099d11dd-c6d9-401d-8c63-991f21876067",
        user_presentation="test",
    )

    cfg = AppConfig(clients={"test": client}, applications={}, token_ttl_seconds=3600)

    token = create_id_token(client, cfg)
    assert isinstance(token, str)
    assert len(token) > 100  # JWT should be reasonably long

    # Verify the token can be decoded
    payload = verify_id_token(token, cfg)
    assert payload is not None
    assert "sub" in payload
    assert "aud" in payload
    assert "iat" in payload
    assert "exp" in payload

    # Check expiration time
    now = int(time.time())
    assert abs(payload["iat"] - now) < 5  # Should be recent
    assert payload["exp"] == payload["iat"] + cfg.token_ttl_seconds


def test_verify_id_token_success():
    """Test successful token verification."""
    client = ClientCredentials(
        client_id="test",
        client_secret="test",
        user_id="22af67ef-d0bd-4861-a7ed-519068ee7d68",
        user_list_id="099d11dd-c6d9-401d-8c63-991f21876067",
        user_presentation="test",
    )

    cfg = AppConfig(clients={"test": client}, applications={}, token_ttl_seconds=3600)

    token = create_id_token(client, cfg)
    payload = verify_id_token(token, cfg)

    assert payload is not None
    assert payload["aud"] == "test"
    assert "sub" in payload
    assert payload["sub"]["user-id"] == client.user_id


def test_verify_id_token_invalid():
    """Test verification of invalid token."""
    cfg = AppConfig(
        clients={
            "test": ClientCredentials(
                client_id="test",
                client_secret="test",
                user_id="22af67ef-d0bd-4861-a7ed-519068ee7d68",
                user_list_id="099d11dd-c6d9-401d-8c63-991f21876067",
                user_presentation="test",
            )
        },
        applications={},
    )

    # Invalid token
    payload = verify_id_token("invalid.token.here", cfg)
    assert payload is None


def test_verify_expired_token():
    """Test verification of expired token."""
    client = ClientCredentials(
        client_id="test",
        client_secret="test",
        user_id="22af67ef-d0bd-4861-a7ed-519068ee7d68",
        user_list_id="099d11dd-c6d9-401d-8c63-991f21876067",
        user_presentation="test",
    )

    cfg = AppConfig(
        clients={"test": client},
        applications={},
        token_ttl_seconds=1,  # Very short expiration
    )

    token = create_id_token(client, cfg)

    # Wait for token to expire
    time.sleep(2)

    payload = verify_id_token(token, cfg)
    assert payload is None  # Should be expired now
