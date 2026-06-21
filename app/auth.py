"""OIDC token endpoint — POST /auth/oidc/token."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .token import create_id_token

router = APIRouter(prefix="/auth/oidc")


@router.post("/token")
async def token_endpoint(
    request: Request,
    settings=Depends(get_settings),
):
    """OAuth2 Client Credentials grant — returns id_token (JWT RS512).

    Client sends Basic auth with any credentials — we accept everything.
    There is only one client configured.

    Note: Although the client sends credentials, they are not actually validated
    (this is a mock gateway for development/testing purposes). Any credentials will be accepted.

    Request:
        Body: grant_type=client_credentials

    Response (200):
        {
            "id_token": "<JWT>",
            "access_token": "Not implemented",
            "token_type": "Bearer"
        }
    """
    config = settings.get_config()

    # Use the first available client (no credential validation)
    if config.clients:
        client = next(iter(config.clients.values()))
    else:
        # Fallback to a minimal client configuration if none exists
        from .config import ClientCredentials
        from .interfaces import UserID, UserListID, UserPresentation

        client = ClientCredentials(
            client_id="default",
            client_secret="default",
            user_id=UserID("00000000-0000-0000-0000-000000000000"),
            user_list_id=UserListID("00000000-0000-0000-0000-000000000000"),
            user_presentation=UserPresentation("Default User"),
        )

    # Read body to validate grant_type
    body = await request.body()
    form_data = body.decode("utf-8") if body else ""
    if "grant_type=client_credentials" not in form_data:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": 1,
                    "status": "INVALID_REQUEST",
                    "message": "Unsupported grant_type.",
                }
            },
        )

    # Generate token
    try:
        id_token = create_id_token(client, config)

        return JSONResponse(
            status_code=200,
            content={
                "id_token": id_token,
                "access_token": "Not implemented",
                "token_type": "Bearer",
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": 10,
                    "status": "INTERNAL_ERROR",
                    "message": f"Failed to generate token: {str(e)}",
                }
            },
        )
