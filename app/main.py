from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pyesb_amqp import AmqpMessage, AmqpServer
from pyesb_amqp.models import E1CMessage
from pyesb_amqp.oidc import router as oidc_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[dict, None]:
    """Start and stop the AMQP server alongside FastAPI."""

    async def amqp_handler(msg: AmqpMessage) -> bool:
        try:
            print(
                E1CMessage.model_validate(msg, from_attributes=True).model_dump_json(
                    indent=2
                )
            )
            return True
        except Exception as exc:
            print(exc)
            return False

    async with AmqpServer(handler=amqp_handler):
        yield {}


app = FastAPI(
    title="1C ESB Gateway",
    description="Compatible server for 1C Enterprise ESB integration (OIDC + AMQP)",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    redirect_slashes=False,
    openapi_url=None,
    swagger_ui_oauth2_redirect_url=None,
    lifespan=lifespan,
)

# Mount all routes from the original oidc app.
app.include_router(oidc_router)
