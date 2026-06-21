#!/usr/bin/env python3
"""Debug script to understand get_config logic."""

import os
from unittest.mock import patch

from app.config import Settings


def test_logic():
    """Test the logic in get_config method."""

    print("=== Test: Environment variable detection ===")
    with patch.dict(os.environ, {"PYESB_HOST": "0.0.0.0", "PYESB_PORT": "9090"}):
        settings = Settings()

        print(f"settings.host: {settings.host}")
        print(f"settings.port: {settings.port}")

        # Create a fresh Settings instance to get values that were set via environment
        env_settings = Settings()

        print(f"env_settings.host: {env_settings.host}")
        print(f"env_settings.port: {env_settings.port}")

        settings_fields = ["host", "port", "jwt_issuer", "token_ttl_seconds"]
        for field_name in settings_fields:
            current_value = getattr(env_settings, field_name)
            default_value = Settings.model_fields[field_name].default

            print(
                f"{field_name}: current={current_value}, default={default_value}, different={current_value != default_value}"
            )


if __name__ == "__main__":
    test_logic()
