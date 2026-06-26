"""Stderr redirect — Rust tracing logs → stdlib logging.

Читает stderr (pyesb-amqp) из pipe и отправляет через
``logging.getLogger("pyesb_amqp")``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Pattern for Python traceback lines (starts with spaces + "File").
# These are NOT valid JSON and come from unhandled exceptions in
# Rust→Python bridge (pyesb-amqp callback threads).
_TRACEBACK_FILE_RE = re.compile(r"^\s+File \"")


def _clean(line: str) -> str:
    """Strip ANSI escape codes from a line."""
    return _ANSI_RE.sub("", line).rstrip("\n\r")


def _detect_stderr_level(raw: str) -> str:
    """Heuristic: determine log level for a plain-text stderr line.

    Traceback lines (``File "..."``), ``Traceback`` headers, and explicit
    ``Error:`` / ``Exception:`` markers are promoted to ``error``.
    """
    stripped = raw.lstrip()
    if _TRACEBACK_FILE_RE.match(raw) or stripped.startswith("Traceback"):
        return "error"
    if stripped.startswith(("Error:", "Exception:", "ValueError:", "TypeError:")):
        return "error"
    return "info"


_LOG = logging.getLogger("pyesb_amqp")


def redirect_stderr() -> tuple[int, int]:
    """Redirect ``stderr`` (fd 2) to a pipe.

    Returns ``(read_fd, write_fd)``.

    The *caller* must close the original stderr when done::

        r_fd, w_fd = redirect_stderr()
        # ... time passes ...
        restore_stderr(r_fd, w_fd)
    """
    original_fd = os.dup(2)  # save original stderr
    r_fd, w_fd = os.pipe()  # create pipe
    os.dup2(w_fd, 2)  # fd 2 -> pipe write end
    os.close(w_fd)  # close extra write fd
    return r_fd, original_fd


def restore_stderr(r_fd: int, original_fd: int) -> None:
    """Restore stderr and close the pipe."""
    os.dup2(original_fd, 2)  # fd 2 -> original stderr
    os.close(original_fd)
    os.close(r_fd)


async def stderr_to_jsonl(r_fd: int) -> None:
    """Read lines from ``r_fd`` and log them through stdlib logging.

    Run as a background asyncio task::

        r_fd, orig_fd = redirect_stderr()
        task = asyncio.create_task(stderr_to_jsonl(r_fd))
        ...
        task.cancel()
        restore_stderr(r_fd, orig_fd)
    """
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, os.read, r_fd, 4096)
            if not line:
                break

            for raw in line.decode("utf-8", errors="replace").splitlines():
                if not raw.strip():
                    continue
                level = _detect_stderr_level(raw)
                _LOG.log(
                    logging._nameToLevel[level.upper()],
                    _clean(raw),
                )
        except OSError:
            break
        except Exception:
            from app.events import LogEvent

            LogEvent().emit(event="stderr_reader_error", level="error")
            await asyncio.sleep(1)
