"""Configuration for the 1C ESB Gateway server."""

import base64
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .interfaces import (
    AccessMode,
    ClientID,
    IPv4Address,
    ProcessID,
    UserID,
    UserListID,
    UserPresentation,
)

BASE_DIR = Path(__file__).resolve().parent.parent
KEYS_DIR = BASE_DIR / "keys"


class ClientCredentials(BaseModel):
    """A registered client (1C application)."""

    client_id: str
    client_secret: str
    user_id: str
    user_list_id: str
    user_presentation: str


class Channel(BaseModel):
    """An AMQP channel exposed by an application."""

    process: str
    process_description: str = ""
    channel: str
    channel_description: str = ""
    access: str


class AppConfig(BaseModel):
    """Top-level server configuration."""

    clients: dict[str, ClientCredentials] = Field(default_factory=dict)
    applications: dict[str, list[Channel]] = Field(default_factory=dict)
    host: IPv4Address = IPv4Address("0.0.0.0")
    port: int = Field(default=9090, ge=1)
    amqp_port: int = Field(default=6698, ge=1)
    jwt_issuer: str = "unused-issuer"
    token_ttl_seconds: int = Field(default=3600, ge=1)


def _hash_client_id(client_id: str) -> str:
    """Produce a base64 SHA-256 hash of the client_id.
    Matches 1C auth-identity.name."""
    digest = hashlib.sha256(client_id.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


DEFAULT_CONFIG = AppConfig(
    clients={
        "test": ClientCredentials(
            client_id="test",
            client_secret="test",
            user_id="00000000-0000-0000-0000-000000000000",
            user_list_id="00000000-0000-0000-0000-000000000000",
            user_presentation="Test User",
        )
    },
    applications={
        "test": [
            Channel(
                process="test_process",
                process_description="Test Process",
                channel="test_channel",
                channel_description="Test Channel",
                access="READ_ONLY",
            )
        ]
    },
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and config file."""

    host: IPv4Address = IPv4Address("0.0.0.0")
    port: int = Field(default=9090, ge=1)
    amqp_port: int = Field(default=6698, ge=1)
    jwt_issuer: str = "unused-issuer"
    token_ttl_seconds: int = Field(default=3600, ge=1)
    config_file: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="PYESB_", env_file=".env", env_file_encoding="utf-8"
    )

    def load_config_from_file(self) -> AppConfig:
        """Load configuration from JSON file if specified."""
        if not self.config_file:
            return AppConfig()

        config_path = Path(self.config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            return AppConfig(**config_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading config file {config_path}: {e}")

    def get_config(self) -> AppConfig:
        """Get the full application configuration."""
        app_config = self.load_config_from_file()

        # Merge with default configuration to ensure clients and applications are always present
        # File values take precedence over defaults
        default_config = DEFAULT_CONFIG.model_copy()

        # Override defaults with file values if they exist
        if app_config.clients:
            default_config.clients = app_config.clients
        if app_config.applications:
            default_config.applications = app_config.applications

        # Apply environment variable overrides for specific fields
        settings_fields = [
            "host",
            "port",
            "amqp_port",
            "jwt_issuer",
            "token_ttl_seconds",
        ]

        for field_name in settings_fields:
            if hasattr(default_config, field_name):
                current_value = getattr(self, field_name)
                setattr(default_config, field_name, current_value)

        return default_config


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
