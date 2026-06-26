"""Entry point: ``uv run --module app``

Разворачивает uvicorn поверх ``aiorun.run()``.
Управление сигналами — uvicorn (``loop.add_signal_handler`` внутри ``serve()``).
После завершения ``server.serve()`` → ``loop.stop()`` → aiorun доотменяет таски.
"""

from __future__ import annotations

import asyncio
import multiprocessing as _mp
import os
import sys

# ── CLI args ─────────────────────────────────────────────────────────────
# Устанавливаем env vars ДО импорта app.config (settings — frozen singleton)
if "--pretty-log" in sys.argv:
    os.environ.setdefault("FWQ_PRETTY_LOG", "true")

import uvicorn
from aiorun import run
from uvicorn.main import STARTUP_FAILURE

from app.config import settings
from app.events import FatalErrorEvent
from app.main import app

_server_ref: list[uvicorn.Server] = []


async def _async_main() -> None:
    """Async entry — uvicorn server под управлением aiorun.

    ``server.serve()``:
      1. startup() — lifespan, сигналы (перезатирает ``signal.signal`` aiorun)
      2. main_loop() — ждёт ``should_exit``
      3. shutdown() — lifespan cleanup → AMQP stop → wait_for_in_flight → scheduler stop
    """
    server: uvicorn.Server | None = None
    try:
        config = uvicorn.Config(
            app,
            host=settings.BIND_HOST,
            port=settings.BIND_PORT,
            reload=False,
            workers=1,
            log_config=None,  # наш JSONL-лог, не uvicorn-дефолт (пишет в stderr)
        )
        server = uvicorn.Server(config=config)
        _server_ref.append(server)

        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        # Если serve() не вызвал shutdown (CancelledError до main_loop)
        if server is not None and server.started:
            await server.shutdown()
        asyncio.get_running_loop().stop()  # aiorun: exit run_forever → cancel → cleanup


def main() -> None:
    """Точка входа. ``workers=1``, ``reload=False`` — жёстко в коде."""
    try:
        run(_async_main(), stop_on_unhandled_errors=True)
    except BaseException as exc:
        FatalErrorEvent(error=f"{type(exc).__name__}: {exc}").emit()
        sys.exit(STARTUP_FAILURE)

    if _server_ref and not _server_ref[0].started:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    if _mp.parent_process() is not None:
        sys.exit("pyesb-webhooker: cannot run in a child process (workers must be 1)")
    main()
