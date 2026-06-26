"""Tests for app.log — stderr level detection."""

from __future__ import annotations

from app.events._stderr import _detect_stderr_level


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
