"""Metadata endpoint — GET /applications/{app}/sys/esb/metadata/channels."""

import logging

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from .config import get_settings
from .token import verify_id_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/applications/{app_name}/sys/esb/metadata/channels")
async def get_channels(
    app_name: str,
    authorization: str | None = Header(default=None),
    settings=Depends(get_settings),
):
    """Return the list of AMQP channels for the given application.

    Requires a valid Bearer token (id_token JWT).

    Response (200):
        [
            {
                "process": "rav::test::Основное::ПроцессИнтеграции1",
                "processDescription": "",
                "channel": "Канал1СНазначение",
                "channelDescription": "",
                "access": "READ_ONLY"
            },
            ...
        ]

    Response (401): UNAUTHENTICATED
    Response (404): Application not found
    """
    # Extract and verify Bearer token
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": 16,
                    "status": "UNAUTHENTICATED",
                    "message": "Missing or invalid authorization header.",
                }
            },
        )

    token = authorization[7:]
    app_config = settings.get_config()
    payload = verify_id_token(token, app_config)
    if payload is None:
        # Log additional debugging info
        logger = logging.getLogger(__name__)
        logger.info(
            f"Token verification failed. Clients: {list(app_config.clients.keys())}"
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": 16,
                    "status": "UNAUTHENTICATED",
                    "message": "Invalid or expired token.",
                }
            },
        )

    # Look up application channels
    channels = app_config.applications.get(app_name)
    if channels is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": 5,
                    "status": "NOT_FOUND",
                    "message": f'Application "{app_name}" not found.',
                    "details": [],
                }
            },
        )

    # Serialize channels to the exact response format from the protocol
    try:
        result = []
        for ch in channels:
            result.append(
                {
                    "process": ch.process,
                    "processDescription": ch.process_description,
                    "channel": ch.channel,
                    "channelDescription": ch.channel_description,
                    "access": ch.access,
                }
            )

        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": 11,
                    "status": "INTERNAL_ERROR",
                    "message": f"Failed to process channel data: {str(e)}",
                    "details": [],
                }
            },
        )
