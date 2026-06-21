"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

# Import the app after ensuring keys are generated
from app.main import app


@pytest.fixture(scope="module")
def test_client():
    """FastAPI test client fixture."""
    with TestClient(app) as client:
        yield client
