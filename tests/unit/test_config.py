"""Unit tests for configuration."""

from app.config import DEFAULT_CONFIG, AppConfig, Channel, ClientCredentials


def test_default_config_structure():
    """Test that default config has expected structure."""
    assert isinstance(DEFAULT_CONFIG, AppConfig)
    assert len(DEFAULT_CONFIG.clients) > 0
    assert len(DEFAULT_CONFIG.applications) > 0

    # Check test client exists
    assert "test" in DEFAULT_CONFIG.clients
    test_client = DEFAULT_CONFIG.clients["test"]
    assert isinstance(test_client, ClientCredentials)
    assert test_client.client_id == "test"
    assert test_client.client_secret == "test"

    # Check test application exists
    assert "test" in DEFAULT_CONFIG.applications
    channels = DEFAULT_CONFIG.applications["test"]
    assert len(channels) > 0
    for channel in channels:
        assert isinstance(channel, Channel)
        assert hasattr(channel, "process")
        assert hasattr(channel, "channel")
        assert hasattr(channel, "access")


def test_config_amqp_port():
    """Test that AMQP port is configured."""
    assert DEFAULT_CONFIG.amqp_port == 6698
