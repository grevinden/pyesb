"""Structured logging — JSONL output via stdlib + structlog bridge.

Usage::

    from app.events import SomeEvent
    SomeEvent(...).emit()

Для stderr redirect (Rust tracing pyesb-amqp) используется
``_jsonl_line()`` — обёртка с ``dt`` и ``ulid``.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import re
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from logging.handlers import QueueHandler, QueueListener
from queue import Queue

import structlog

from .config import settings

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


def _jsonl_line(raw: str, level: str | None = None) -> str:
    """Wrap a plain-text line in JSONL, stripping ANSI codes.

    Добавляет ``dt`` и ``ulid`` для совместимости с форматом
    ``LogEvent``-моделей. ``timestamp`` (от structlog) дублирует
    ``dt`` — это нормально для stderr-потока (нет Pydantic-модели).
    """
    if level is None:
        level = _detect_stderr_level(raw)
    import json as _json_mod
    from datetime import datetime, timezone

    from ulid import ULID

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return _json_mod.dumps(
        {
            "dt": ts,
            "ulid": str(ULID()),
            "event": _clean(raw),
            "level": level,
            "logger": "pyesb_amqp",
            "timestamp": ts,
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# stderr redirect — Rust tracing logs -> JSONL
# ---------------------------------------------------------------------------

_log_listener: QueueListener | None = None


async def _async_print(text: str) -> None:
    """Write ``text`` to stdout (fd 1) without blocking the event loop."""
    data = (text + "\n").encode("utf-8", errors="replace")
    await asyncio.to_thread(os.write, 1, data)


_original_stderr: int | None = None
_stderr_r: int | None = None
_stderr_w: int | None = None


def redirect_stderr() -> tuple[int, int]:
    """Redirect ``stderr`` (fd 2) to a pipe.

    Returns ``(read_fd, write_fd)``.

    The *caller* must close the original stderr when done::

        r_fd, w_fd = redirect_stderr()
        # ... time passes ...
        restore_stderr(r_fd, w_fd)
    """
    global _original_stderr, _stderr_r, _stderr_w
    _original_stderr = os.dup(2)  # save original stderr
    _stderr_r, _stderr_w = os.pipe()  # create pipe
    os.dup2(_stderr_w, 2)  # fd 2 -> pipe write end
    os.close(_stderr_w)  # close extra write fd
    return _stderr_r, _original_stderr


def restore_stderr(r_fd: int, original_fd: int) -> None:
    """Restore stderr and close the pipe."""
    os.dup2(original_fd, 2)  # fd 2 -> original stderr
    os.close(original_fd)
    os.close(r_fd)


async def stderr_to_jsonl(r_fd: int) -> None:
    """Read lines from ``r_fd`` and write JSONL to stdout.

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
            import json as _json_mod

            for raw in line.decode("utf-8", errors="replace").splitlines():
                if not raw.strip():
                    continue
                # Already valid JSON -> pass through
                try:
                    _json_mod.loads(_clean(raw))
                    output = raw
                except (_json_mod.JSONDecodeError, ValueError):
                    output = _jsonl_line(raw)
                await _async_print(output)
        except OSError:
            break
        except Exception:
            from app.events import StderrReaderErrorEvent

            StderrReaderErrorEvent().emit()
            await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# structlog processor: inject message_id from contextvars
# ---------------------------------------------------------------------------


def _add_context_vars(
    logger: structlog.stdlib.BoundLogger,
    method_name: str,
    event_dict: MutableMapping[str, object],
) -> MutableMapping[str, object]:
    """Inject ``message_id`` and ``trace_id`` from contextvars if set.

    Позволяет автоматически добавлять ``message_id`` и ``trace_id``
    во все structlog-логи внутри ``deliver_payload`` без явной передачи
    в каждый вызов.
    """
    from app.context import message_id_var, trace_id_var

    msg_id = message_id_var.get(None)
    if msg_id is not None:
        event_dict["message_id"] = msg_id

    tr_id = trace_id_var.get(None)
    if tr_id is not None:
        event_dict["trace_id"] = tr_id

    return event_dict


# ---------------------------------------------------------------------------
# Non-blocking logging: QueueHandler + QueueListener
# ---------------------------------------------------------------------------


class _StructlogAwareQueueHandler(QueueHandler):
    """QueueHandler that preserves structlog's ``event_dict`` in ``record.msg``.

    The default :meth:`QueueHandler.prepare` calls :meth:`Handler.format`
    which serializes ``record.msg`` to a string (via ``str(record.msg)``).
    For structlog records this **destroys** the ``event_dict`` dict that
    :class:`structlog.stdlib.ProcessorFormatter` expects at format time.

    Since we use an **in-process** ``queue.Queue`` (not multiprocessing),
    we don't need pickleability. Override ``prepare()`` to preserve dict
    ``msg`` untouched.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        if isinstance(record.msg, dict):
            # Structlog record — keep the event_dict as-is.
            # The default prepare() would call Handler.format() which
            # does str(record.msg) — destroying the dict.
            return record
        # Stdlib string record — default prepare is safe.
        return super().prepare(record)


def start_logging_queue(maxsize: int | None = None) -> None:
    """Wrap root logger handlers with ``QueueHandler`` + ``QueueListener``.

    Заменяет синхронный ``StreamHandler`` (блокирует event loop при
    записи в stdout/pipe) на неблокирующий:

    * ``logging.info()`` -> ``QueueHandler`` -> ``queue.Queue`` (быстрая put).
    * Фоновый поток ``QueueListener`` читает из очереди и вызывает
      оригинальные хендлеры (``StreamHandler`` + ``JsonlFormatter``).

    Вызывать **после** ``load_logging_config()``.
    """
    global _log_listener

    root = logging.getLogger()
    if _log_listener is not None or not root.handlers:
        return

    if maxsize is None:
        maxsize = settings.LOG_QUEUE_MAXSIZE
    q: Queue[logging.LogRecord] = Queue(maxsize=maxsize)
    qh = _StructlogAwareQueueHandler(q)

    # Переносим существующие хендлеры в QueueListener
    original_handlers = root.handlers[:]
    root.handlers.clear()
    root.addHandler(qh)

    _log_listener = QueueListener(q, *original_handlers, respect_handler_level=True)
    _log_listener.start()


def stop_logging_queue() -> None:
    """Flush and stop the ``QueueListener``.

    Блокируется до записи всех накопившихся записей (последний flush).
    """
    global _log_listener
    if _log_listener is not None:
        _log_listener.stop()
        _log_listener = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_logging_config() -> None:
    """Configure structlog + stdlib logging bridge.

    Все записи (structlog и stdlib) проходят через
    ``structlog.stdlib.ProcessorFormatter``, что гарантирует
    единый формат JSONL для всех источников.

    **Structlog-записи** (``events.py``):
        ``processors`` → ``wrap_for_formatter`` → ``ProcessorFormatter`` → JSON

    **Stdlib-записи** (apscheduler, uvicorn):
        ``foreign_pre_chain`` → ``ProcessorFormatter`` → JSON

    Call **before** the main event loop starts (inside ``lifespan``).
    """
    # Idempotency guard — не настраиваем дважды (важно для тестов)
    if logging.getLogger().hasHandlers():
        return
    # ── 1. Configure structlog processors ───────────────────────────
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            _add_context_vars,  # inject message_id, trace_id from contextvars
            # wrap_for_formatter — финальный процессор для structlog-записей.
            # Он преобразует event_dict в строку и кладёт её в LogRecord.msg.
            # Затем ProcessorFormatter забирает её и рендерит через processor.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── 2. Setup stdlib handler with ProcessorFormatter ─────────────
    # ProcessorFormatter — единый форматтер для всех stdlib handler-ов.
    #   * processor: финальный рендеринг (JSON) — применяется ко ВСЕМ записям
    #   * foreign_pre_chain: цепочка для stdlib-записей (НЕ structlog)
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # ── 3. Set levels for third-party loggers ───────────────────────
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)


@asynccontextmanager
async def stderr_redirect_lifespan() -> AsyncGenerator[None, None]:
    """Context manager that redirects stderr -> JSONL during its lifetime.

    Use inside the FastAPI ``lifespan``::

        @asynccontextmanager
        async def lifespan(app):
            async with stderr_redirect_lifespan():
                yield
    """
    from app.tasks import safe_create_task

    r_fd, original_fd = redirect_stderr()
    task = safe_create_task(
        stderr_to_jsonl(r_fd),
        name="stderr-to-jsonl",
    )
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
