"""Unit tests for authentication utilities."""

import base64

from app.auth_utils import parse_basic_auth


def test_parse_basic_auth_valid():
    """Test parsing valid Basic auth header."""
    encoded = base64.b64encode(b"user:pass").decode("ascii")
    result = parse_basic_auth(f"Basic {encoded}")
    assert result == ("user", "pass")


def test_parse_basic_auth_invalid_format():
    """Test parsing invalid Basic auth format."""
    result = parse_basic_auth("Bearer token123")
    assert result is None


def test_parse_basic_auth_malformed_base64():
    """Test parsing malformed Base64."""
    result = parse_basic_auth("Basic invalidbase64===")
    assert result is None


def test_parse_basic_auth_no_colon():
    """Test parsing Basic auth without colon separator."""
    encoded = base64.b64encode(b"userpass").decode("ascii")
    result = parse_basic_auth(f"Basic {encoded}")
    assert result is not None
