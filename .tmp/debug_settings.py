#!/usr/bin/env python3
"""Debug script to understand Pydantic settings behavior."""

import os
from unittest.mock import patch

from app.config import Settings


def test_env_detection():
    """Test how to detect if environment variables are set."""

    print("=== Test 1: Default settings ===")
    settings1 = Settings()
    print(f"host: {settings1.host}")
    print(f"port: {settings1.port}")
    print(f"model_dump(): {settings1.model_dump()}")

    print("\n=== Test 2: With environment variables ===")
    with patch.dict(os.environ, {"PYESB_HOST": "0.0.0.0", "PYESB_PORT": "9090"}):
        settings2 = Settings()
        print(f"host: {settings2.host}")
        print(f"port: {settings2.port}")
        print(f"model_dump(): {settings2.model_dump()}")

    print("\n=== Test 3: Check model_fields ===")
    print(
        f"Settings.model_fields['host'].default: {Settings.model_fields['host'].default}"
    )
    print(
        f"Settings.model_fields['port'].default: {Settings.model_fields['port'].default}"
    )


if __name__ == "__main__":
    test_env_detection()
