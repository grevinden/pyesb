#!/usr/bin/env python3
"""Debug script to understand Pydantic settings behavior."""

import os
from unittest.mock import patch

from pydantic_settings import BaseSettings, SettingsConfigDict


def test_with_patch():
    """Test with patch.dict."""

    class SimpleSettings(BaseSettings):
        host: str = "0.0.0.0"
        port: int = 9090

        model_config = SettingsConfigDict(env_prefix="PYESB_")

    print("=== Test 1: Default settings ===")
    settings1 = SimpleSettings()
    print(f"host: {settings1.host}")
    print(f"port: {settings1.port}")

    print("\n=== Test 2: With patch.dict ===")
    with patch.dict(os.environ, {"PYESB_HOST": "127.0.0.1", "PYESB_PORT": "8080"}):
        settings2 = SimpleSettings()
        print(f"host: {settings2.host}")
        print(f"port: {settings2.port}")


if __name__ == "__main__":
    test_with_patch()
