"""Tests for app.log — stderr level detection, JSONL formatting."""

from __future__ import annotations

import json

from app.log import _detect_stderr_level, _jsonl_line


class TestDetectStderrLevel:
    def test_traceback_file_line(self) -> None:
        raw = '  File "/some/path.py", line 10, in func'
        assert _detect_stderr_level(raw) == "error"

    def test_traceback_header(self) -> None:
        raw = "Traceback (most recent call last):"
        assert _detect_stderr_level(raw) == "error"

    def test_exception_marker(self) -> None:
        raw = "ValueError: something broke"
        assert _detect_stderr_level(raw) == "error"

    def test_info_level(self) -> None:
        raw = "[2024-01-01T00:00:00Z DEBUG] some log message"
        assert _detect_stderr_level(raw) == "info"

    def test_empty_string(self) -> None:
        assert _detect_stderr_level("") == "info"


class TestJsonlLine:
    def test_returns_valid_json(self) -> None:
        raw = "hello world"
        line = _jsonl_line(raw)
        parsed = json.loads(line)
        assert parsed["event"] == "hello world"
        assert parsed["level"] == "info"
        assert parsed["logger"] == "pyesb_amqp"

    def test_dt_and_ulid_present(self) -> None:
        raw = "test"
        line = _jsonl_line(raw)
        parsed = json.loads(line)
        assert "dt" in parsed
        assert "ulid" in parsed
        assert len(parsed["ulid"]) == 26  # ULID v1

    def test_ansi_stripped(self) -> None:
        raw = "\x1b[31mred message\x1b[0m"
        line = _jsonl_line(raw)
        parsed = json.loads(line)
        assert parsed["event"] == "red message"
        assert "\x1b" not in parsed["event"]

    def test_level_override(self) -> None:
        raw = "error message"
        line = _jsonl_line(raw, level="error")
        parsed = json.loads(line)
        assert parsed["level"] == "error"

    def test_auto_detect_error(self) -> None:
        raw = "Error: connection refused"
        line = _jsonl_line(raw)  # no level override
        parsed = json.loads(line)
        assert parsed["level"] == "error"
