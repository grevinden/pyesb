"""Tests for HTTP header validation — CRLF injection prevention."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.delivery.headers import (
    HeaderTuple,
    validate_header_dict,
    validate_header_pairs,
)
from app.ingress.models import PayloadSchema

# ── Pydantic-типы ──────────────────────────────────────────────────────


class _ModelWithHeaders(BaseModel):
    headers: set[HeaderTuple] | None = None


class TestSafeHeaderKey:
    """Pydantic-валидация ключа заголовка."""

    def test_valid_key(self) -> None:
        model = _ModelWithHeaders(headers={("Content-Type", "application/json")})
        assert model.headers is not None
        key, val = next(iter(model.headers))
        assert key == "Content-Type"
        assert val == "application/json"

    def test_cr_in_key(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("Content-Type\r", "application/json")})

    def test_lf_in_key(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("Content-Type\n", "application/json")})

    def test_crlf_in_key(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("Content-Type\r\n", "application/json")})

    def test_empty_key(self) -> None:
        """Пустой ключ — допустим."""
        model = _ModelWithHeaders(headers={("", "value")})
        assert model.headers is not None

    def test_valid_multiple_headers(self) -> None:
        model = _ModelWithHeaders(
            headers={
                ("X-Api-Key", "secret123"),
                ("Authorization", "Bearer token"),
                ("X-Custom", "value"),
            }
        )
        assert model.headers is not None
        assert len(model.headers) == 3

    def test_none_headers(self) -> None:
        model = _ModelWithHeaders(headers=None)
        assert model.headers is None

    def test_empty_set(self) -> None:
        model = _ModelWithHeaders(headers=set())
        assert model.headers is not None
        assert len(model.headers) == 0


class TestSafeHeaderValue:
    """Pydantic-валидация значения заголовка."""

    def test_cr_in_value(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("X-Custom", "value\r")})

    def test_lf_in_value(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("X-Custom", "value\n")})

    def test_crlf_in_value(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("X-Custom", "value\r\n")})

    def test_crlf_in_both(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("X-Custom\r\n", "value\r\n")})

    def test_multiline_within_value(self) -> None:
        r"""Несколько строк через \n — тоже запрещено."""
        with pytest.raises(ValidationError, match="CR/LF"):
            _ModelWithHeaders(headers={("X-Custom", "line1\nline2")})

    def test_special_chars_allowed(self) -> None:
        """Спецсимволы без CR/LF — допустимы."""
        model = _ModelWithHeaders(headers={("X-Custom", r"!@#$%^&*()_+-=[]{}|;':\",./<>?~")})
        assert model.headers is not None

    def test_unicode_allowed(self) -> None:
        """Юникод без CR/LF — допустим."""
        model = _ModelWithHeaders(headers={("X-Custom", "Привет, мир! 🌍")})
        assert model.headers is not None

    def test_spaces_allowed(self) -> None:
        """Пробелы в значении — допустимы."""
        model = _ModelWithHeaders(headers={("X-Custom", "value with spaces")})
        assert model.headers is not None


# ── PayloadSchema integration ──────────────────────────────────────────


class TestPayloadSchemaHeaders:
    """PayloadSchema использует HeaderTuple."""

    def test_valid_headers(self) -> None:
        schema = PayloadSchema(
            url="http://example.com/hook",
            body={"key": "value"},
            headers={("X-Api-Key", "secret")},
            timeout=10,
            pause=5,
            ttl=60,
        )
        assert schema.headers == {("X-Api-Key", "secret")}

    def test_crlf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CR/LF"):
            PayloadSchema(
                url="http://example.com/hook",
                body={"key": "value"},
                headers={("X-Api-Key", "secret\r\n")},
                timeout=10,
                pause=5,
                ttl=60,
            )

    def test_json_roundtrip_rejects_crlf(self) -> None:
        """CRLF-заголовок отвергается даже при создании через JSON."""
        import json

        payload = json.dumps({
            "url": "http://example.com/hook",
            "body": {"key": "value"},
            "headers": [["X-Api-Key", "secret\r\n"]],
            "timeout": 10,
            "pause": 5,
            "ttl": 60,
        })
        with pytest.raises(ValidationError, match="CR/LF"):
            PayloadSchema.model_validate_json(payload)

    def test_dict_roundtrip_rejects_crlf(self) -> None:
        """CRLF-заголовок отвергается при создании через dict."""
        with pytest.raises(ValidationError, match="CR/LF"):
            PayloadSchema.model_validate({
                "url": "http://example.com/hook",
                "body": {"key": "value"},
                "headers": [["X-Api-Key", "secret\n"]],
                "timeout": 10,
                "pause": 5,
                "ttl": 60,
            })

    def test_no_headers(self) -> None:
        schema = PayloadSchema(
            url="http://example.com/hook",
            body={"key": "value"},
            timeout=10,
            pause=5,
            ttl=60,
        )
        assert schema.headers is None


# ── Runtime-валидация (validate_header_pairs) ──────────────────────────


class TestValidateHeaderPairs:
    """validate_header_pairs — runtime проверка списка пар."""

    def test_none(self) -> None:
        assert validate_header_pairs(None) is None

    def test_valid(self) -> None:
        headers = [("X-Key", "value"), ("Authorization", "Bearer token")]
        result = validate_header_pairs(headers)
        assert result == headers

    def test_empty_list(self) -> None:
        assert validate_header_pairs([]) == []

    def test_cr_in_key(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_pairs([("Key\r", "value")])

    def test_lf_in_value(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_pairs([("Key", "value\n")])

    def test_crlf_in_value(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_pairs([("Key", "value\r\n")])

    def test_multiple_pairs_one_invalid(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_pairs([
                ("Good", "value"),
                ("Bad\n", "value"),
                ("Also-Good", "value"),
            ])


# ── Runtime-валидация (validate_header_dict) ───────────────────────────


class TestValidateHeaderDict:
    """validate_header_dict — runtime проверка словаря."""

    def test_none(self) -> None:
        assert validate_header_dict(None) is None

    def test_valid(self) -> None:
        headers = {"X-Key": "value", "Authorization": "Bearer token"}
        result = validate_header_dict(headers)
        assert result == headers

    def test_empty_dict(self) -> None:
        assert validate_header_dict({}) == {}

    def test_cr_in_key(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_dict({"Key\r": "value"})

    def test_lf_in_value(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_dict({"Key": "value\n"})

    def test_crlf_in_value(self) -> None:
        with pytest.raises(ValueError, match="CR/LF"):
            validate_header_dict({"Key": "value\r\n"})
