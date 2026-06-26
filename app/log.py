"""Structured logging — JSONL output via stdlib + structlog bridge.

Usage::

    from app.log import get_logger

    logger = get_logger(__name__)
    logger.info("msg", key="value")
"""

from __future__ import annotations

import asyncio
import json as json_module
import logging.config
import os
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import yaml


class JsonlFormatter(logging.Formatter):
    """Convert any log record to JSONL.

    * structlog records  → msg is already JSON → output as-is
    * uvicorn / stdlib   → wrap plain text in JSON
    """

    def format(self, record: logging.LogRecord) -> str:
        raw = record.getMessage()
        try:
            json_module.loads(raw)
            return raw
        except (json_module.JSONDecodeError, ValueError):
            pass
        return json_module.dumps(
            {
                "event": raw,
                "level": record.levelname.lower(),
                "logger": record.name,
                "module": record.module,
                "line": record.lineno,
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            },
            default=str,
        )


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean(line: str) -> str:
    """Strip ANSI escape codes from a line."""
    return _ANSI_RE.sub("", line).rstrip("\n\r")


def _jsonl_line(raw: str, level: str = "info") -> str:
    """Wrap a plain-text line in JSONL, stripping ANSI codes."""
    return json_module.dumps(
        {"event": _clean(raw), "level": level, "logger": "pyesb_amqp"},
        default=str,
    )


# ---------------------------------------------------------------------------
# stderr redirect — Rust tracing logs → JSONL
# ---------------------------------------------------------------------------

_original_stderr: int | None = None
_stderr_r: int | None = None
_stderr_w: int | None = None


def redirect_stderr() -> tuple[int, int]:
    """Redirect ``stderr`` (fd 2) to a pipe.

    Returns ``(read_fd, write_fd)``.

    The *caller* must close the original stderr when done::

        r_fd, w_fd = redirect_stderr()
        # … time passes …
        restore_stderr(r_fd, w_fd)
    """
    global _original_stderr, _stderr_r, _stderr_w
    _original_stderr = os.dup(2)  # save original stderr
    _stderr_r, _stderr_w = os.pipe()  # create pipe
    os.dup2(_stderr_w, 2)  # fd 2 → pipe write end
    os.close(_stderr_w)  # close extra write fd
    return _stderr_r, _original_stderr


def restore_stderr(r_fd: int, original_fd: int) -> None:
    """Restore stderr and close the pipe."""
    os.dup2(original_fd, 2)  # fd 2 → original stderr
    os.close(original_fd)
    os.close(r_fd)


async def stderr_to_jsonl(r_fd: int) -> None:
    """Read lines from ``r_fd`` and write JSONL to stdout.

    Run as a background asyncio task::

        r_fd, orig_fd = redirect_stderr()
        task = asyncio.create_task(stderr_to_jsonl(r_fd))
        …
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
                # Already valid JSON → pass through
                try:
                    json_module.loads(_clean(raw))
                    output = raw
                except (json_module.JSONDecodeError, ValueError):
                    output = _jsonl_line(raw)
                print(output, flush=True)
        except OSError:
            break


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_logging_config(config_path: str = "logging.yaml") -> None:
    """Load ``logging.yaml`` and bridge structlog → stdlib.

    Call **before** the main event loop starts (inside ``lifespan``).
    """
    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    with path.open() as f:
        cfg = yaml.safe_load(f)
    logging.config.dictConfig(cfg)

    # structlog → stdlib bridging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def stderr_redirect_lifespan() -> AsyncGenerator[None, None]:
    """Context manager that redirects stderr → JSONL during its lifetime.

    Use inside the FastAPI ``lifespan``::

        @asynccontextmanager
        async def lifespan(app):
            async with stderr_redirect_lifespan():
                yield
    """
    r_fd, original_fd = redirect_stderr()
    task = asyncio.create_task(stderr_to_jsonl(r_fd))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        restore_stderr(r_fd, original_fd)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with given name."""
    return structlog.get_logger(name or __name__)
