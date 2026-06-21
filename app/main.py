"""1C ESB Gateway — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .amqp_server import NonBlockingAMQPContainer
from .auth import router as auth_router
from .config import get_settings
from .metadata import router as metadata_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown lifecycle."""
    settings = get_settings()
    config = settings.get_config()

    # Use non-blocking AMQP container
    container = NonBlockingAMQPContainer(host=config.host, port=config.amqp_port)
    container.start()

    logger.info(
        "1C ESB Gateway started — HTTP:%d, AMQP:%d", config.port, config.amqp_port
    )

    try:
        yield
    finally:
        container.stop()


app = FastAPI(
    title="1C ESB Gateway",
    description="Compatible server for 1C Enterprise ESB integration (OIDC + AMQP)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(metadata_router)


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    config = settings.get_config()

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        log_level="info",
    )
