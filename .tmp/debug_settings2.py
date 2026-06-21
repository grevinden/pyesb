#!/usr/bin/env python3
"""Debug script to understand Pydantic settings behavior."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def test_simple_settings():
    """Test with a simple settings class."""

    class SimpleSettings(BaseSettings):
        host: str = "0.0.0.0"
        port: int = 9090

        model_config = SettingsConfigDict(env_prefix="PYESB_", env_file=".env")

    print("=== Test 1: Default settings ===")
    settings1 = SimpleSettings()
    print(f"host: {settings1.host}")
    print(f"port: {settings1.port}")

    print("\n=== Test 2: With environment variables ===")
    os.environ["PYESB_HOST"] = "127.0.0.1"
    os.environ["PYESB_PORT"] = "8080"

    settings2 = SimpleSettings()
    print(f"host: {settings2.host}")
    print(f"port: {settings2.port}")

    # Clean up
    del os.environ["PYESB_HOST"]
    del os.environ["PYESB_PORT"]


if __name__ == "__main__":
    test_simple_settings()
