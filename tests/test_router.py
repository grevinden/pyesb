"""Tests for app.router — resolve_trace_id, first_str."""

from __future__ import annotations

from uuid import uuid4

from app.ingress.router import first_str, resolve_trace_id


class TestResolveTraceId:
    def test_valid_uuid(self) -> None:
        tid = str(uuid4())
        result = resolve_trace_id(tid)
        assert result == tid

    def test_none(self) -> None:
        result = resolve_trace_id(None)
        assert result is None

    def test_empty_string(self) -> None:
        result = resolve_trace_id("")
        assert result is None

    def test_invalid_uuid(self) -> None:
        result = resolve_trace_id("not-a-uuid")
        assert result is None


class TestFirstStr:
    def test_str_input(self) -> None:
        assert first_str("hello") == "hello"

    def test_list_input(self) -> None:
        assert first_str(["a", "b"]) == "a"

    def test_empty_list(self) -> None:
        assert first_str([]) is None

    def test_none_input(self) -> None:
        assert first_str(None) is None
