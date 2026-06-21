#!/usr/bin/env python3
"""Debug script to understand get_config behavior."""

import json
import os
from unittest.mock import patch

from app.config import Settings


def test_get_config():
    """Test get_config method."""

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
        print("=== Test 1: get_config without environment variables ===")
        settings1 = Settings(config_file=config_file)
        app_config1 = settings1.get_config()
        print(f"app_config.host: {app_config1.host}")
        print(f"app_config.port: {app_config1.port}")

        print("\n=== Test 2: get_config with environment variables ===")
        with patch.dict(os.environ, {"PYESB_HOST": "0.0.0.0", "PYESB_PORT": "9090"}):
            settings2 = Settings(config_file=config_file)
            app_config2 = settings2.get_config()
            print(f"app_config.host: {app_config2.host}")
            print(f"app_config.port: {app_config2.port}")

    finally:
        # Clean up
        os.unlink(config_file)


if __name__ == "__main__":
    test_get_config()
