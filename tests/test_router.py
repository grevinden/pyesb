"""Tests for app.router — resolve_trace_id, first_str."""

from __future__ import annotations

from uuid import uuid4

from app.router import first_str, resolve_trace_id


class TestResolveTraceId:
    def test_from_body_trace_id(self) -> None:
        trace_id = uuid4()
        result = resolve_trace_id(trace_id, None)
        assert result == str(trace_id)

    def test_from_header(self) -> None:
        trace_id = uuid4()
        headers = {("X-Trace-Id", str(trace_id))}
        result = resolve_trace_id(None, headers)
        assert result == str(trace_id)

    def test_header_case_insensitive(self) -> None:
        trace_id = uuid4()
        headers = {("x-trace-id", str(trace_id))}
        result = resolve_trace_id(None, headers)
        assert result == str(trace_id)

    def test_no_trace_id(self) -> None:
        result = resolve_trace_id(None, None)
        assert result is None

    def test_invalid_uuid_in_header(self) -> None:
        headers = {("X-Trace-Id", "not-a-uuid")}
        result = resolve_trace_id(None, headers)
        assert result is None

    def test_prefers_body_over_header(self) -> None:
        body_trace = uuid4()
        header_trace = uuid4()
        headers = {("X-Trace-Id", str(header_trace))}
        result = resolve_trace_id(body_trace, headers)
        assert result == str(body_trace)  # body wins
        assert result != str(header_trace)


class TestFirstStr:
    def test_str_input(self) -> None:
        assert first_str("hello") == "hello"

    def test_list_input(self) -> None:
        assert first_str(["a", "b"]) == "a"

    def test_empty_list(self) -> None:
        assert first_str([]) is None

    def test_none_input(self) -> None:
        assert first_str(None) is None
