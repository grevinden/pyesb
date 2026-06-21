"""JWT token generation — RS512, matching the 1C ESB Gateway protocol."""

import base64
import hashlib
import logging
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .config import KEYS_DIR, AppConfig, ClientCredentials
from .interfaces import ClientID

logger = logging.getLogger(__name__)


def _ensure_keys() -> tuple:
    """Load or generate RSA key pair (2048-bit).
    Returns (private_key_pem_bytes, public_key_pem_bytes)."""
    private_path = KEYS_DIR / "private.pem"
    public_path = KEYS_DIR / "public.pem"

    if private_path.exists() and public_path.exists():
        return private_path.read_bytes(), public_path.read_bytes()

    # Generate new keys
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return private_pem, public_pem


def create_id_token(client: ClientCredentials, cfg: AppConfig) -> str:
    """Create an id_token JWT matching the 1C ESB capture exactly.

    Claim structure (from protocol.md):
    {
      "iss": "unused-issuer",
      "sub": {
        "user-id": "...",
        "user-list-id": "...",
        "user-presentation": "...",
        "auth-identity": {
          "name": "<base64-sha256(client_id)>",
          "domain": "user_tokens"
        }
      },
      "aud": "<client_id>",
      "iat": <now>,
      "exp": <now + 3600>,
      "at_hash": "AccessToken hash (not implemented)"
    }
    """
    try:
        private_pem, _ = _ensure_keys()

        now = int(time.time())
        auth_identity_name = _hash_client_id(client.client_id)

        payload = {
            "iss": cfg.jwt_issuer,
            "sub": {
                "user-id": client.user_id,
                "user-list-id": client.user_list_id,
                "user-presentation": client.user_presentation,
                "auth-identity": {
                    "name": auth_identity_name,
                    "domain": "user_tokens",
                },
            },
            "aud": client.client_id,
            "iat": now,
            "exp": now + cfg.token_ttl_seconds,
            "at_hash": "AccessToken hash (not implemented)",
        }

        token = jwt.encode(payload, private_pem, algorithm="RS512")
        return token
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Failed to create JWT token: %s", e)
        raise


def _hash_client_id(client_id: str) -> str:
    """Base64-encoded SHA-256 of client_id — mirrors config._hash_client_id."""
    digest = hashlib.sha256(client_id.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_id_token(token: str, cfg: AppConfig) -> dict | None:
    """Verify and decode an id_token. Returns payload dict or None."""
    _, public_pem = _ensure_keys()

    try:
        payload = jwt.decode(
            token,
            public_pem,
            algorithms=["RS512"],
            audience=list(cfg.clients.keys()),
            options={"verify_iss": False, "verify_sub": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
