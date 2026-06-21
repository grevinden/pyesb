#!/usr/bin/env python3
"""Debug script to understand get_config logic in detail."""

import json
import os
from unittest.mock import patch

from app.config import Settings


def test_get_config_detailed():
    """Test get_config method with detailed debugging."""

    # Create a temporary config file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_data = {
            "host": "127.0.0.1",
            "port": 8080,
            "clients": {},
            "applications": {},
        }
        json.dump(config_data, f)
        config_file = f.name

    try:
        print("=== Test: get_config with environment variables ===")
        with patch.dict(os.environ, {"PYESB_HOST": "0.0.0.0", "PYESB_PORT": "9090"}):
            settings = Settings(config_file=config_file)

            print(f"settings.host: {settings.host}")
            print(f"settings.port: {settings.port}")

            # Load config from file first
            app_config = settings.load_config_from_file()
            print(f"app_config (from file).host: {app_config.host}")
            print(f"app_config (from file).port: {app_config.port}")

            # Now apply the logic from get_config
            settings_fields = ["host", "port", "jwt_issuer", "token_ttl_seconds"]
            for field_name in settings_fields:
                if hasattr(app_config, field_name):
                    current_value = getattr(settings, field_name)
                    file_value = getattr(app_config, field_name)

                    print(
                        f"{field_name}: current={current_value}, file={file_value}, different={current_value != file_value}"
                    )

                    if current_value != file_value:
                        setattr(app_config, field_name, current_value)

            print(f"app_config (after override).host: {app_config.host}")
            print(f"app_config (after override).port: {app_config.port}")

    finally:
        # Clean up
        os.unlink(config_file)


if __name__ == "__main__":
    test_get_config_detailed()
