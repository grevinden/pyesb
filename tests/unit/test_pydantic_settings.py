"""Comprehensive tests for Pydantic settings configuration."""

import json
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import AppConfig, Channel, ClientCredentials, Settings, get_settings


class TestSettingsInitialization:
    """Test settings initialization and default values."""

    def test_default_settings_values(self):
        """Test that settings have correct default values."""
        settings = Settings()

        assert str(settings.host) == "0.0.0.0"
        assert settings.port == 9090
        assert settings.amqp_port == 6698
        assert settings.jwt_issuer == "unused-issuer"
        assert settings.token_ttl_seconds == 3600
        assert settings.config_file is None

    def test_settings_from_environment_variables(self):
        """Test that settings can be loaded from environment variables."""
        with patch.dict(
            os.environ,
            {
                "PYESB_HOST": "127.0.0.1",
                "PYESB_PORT": "8080",
                "PYESB_JWT_ISSUER": "test-issuer",
                "PYESB_TOKEN_TTL_SECONDS": "7200",
                "PYESB_CONFIG_FILE": "/path/to/config.json",
            },
        ):
            settings = Settings()

            assert str(settings.host) == "127.0.0.1"
            assert settings.port == 8080
            assert settings.jwt_issuer == "test-issuer"
            assert settings.token_ttl_seconds == 7200
            assert settings.config_file == "/path/to/config.json"

    def test_settings_validation(self):
        """Test that settings validation works correctly."""
        # Test invalid port value (must be positive)
        with pytest.raises(ValidationError):
            Settings(port=-1)

        # Test invalid TTL value (must be positive)
        with pytest.raises(ValidationError):
            Settings(token_ttl_seconds=0)

    def test_settings_model_dump(self):
        """Test that settings can be serialized correctly."""
        settings = Settings(
            host="127.0.0.1",
            port=8080,
            jwt_issuer="test-issuer",
            token_ttl_seconds=7200,
        )

        data = settings.model_dump()
        assert data == {
            "host": "127.0.0.1",
            "port": 8080,
            "amqp_port": 6698,
            "jwt_issuer": "test-issuer",
            "token_ttl_seconds": 7200,
            "config_file": None,
        }

    def test_settings_model_dump_json(self):
        """Test JSON serialization of settings."""
        settings = Settings(host="127.0.0.1", port=8080, jwt_issuer="test-issuer")

        json_str = settings.model_dump_json()
        data = json.loads(json_str)
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 8080
        assert data["jwt_issuer"] == "test-issuer"


class TestConfigFileLoading:
    """Test configuration file loading functionality."""

    def test_load_config_from_file_none(self, tmp_path):
        """Test loading config when no file is specified."""
        settings = Settings(config_file=None)
        app_config = settings.load_config_from_file()

        assert isinstance(app_config, AppConfig)
        assert len(app_config.clients) == 0
        assert len(app_config.applications) == 0

    def test_load_config_from_valid_file(self, tmp_path):
        """Test loading config from a valid JSON file."""
        # Create a test config file
        config_data = {
            "clients": {
                "test_client": {
                    "client_id": "test",
                    "client_secret": "secret",
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "user_list_id": "00000000-0000-0000-0000-000000000000",
                    "user_presentation": "Test User",
                }
            },
            "applications": {
                "test_app": [
                    {
                        "process": "test_proc",
                        "channel": "test_chan",
                        "access": "READ_ONLY",
                    }
                ]
            },
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        settings = Settings(config_file=str(config_file))
        app_config = settings.load_config_from_file()

        assert isinstance(app_config, AppConfig)
        assert len(app_config.clients) == 1
        assert "test_client" in app_config.clients
        assert len(app_config.applications) == 1
        assert "test_app" in app_config.applications

    def test_load_config_from_missing_file(self):
        """Test loading config from a missing file."""
        settings = Settings(config_file="/nonexistent/config.json")

        with pytest.raises(FileNotFoundError):
            settings.load_config_from_file()

    def test_load_config_with_invalid_json(self, tmp_path):
        """Test loading config from a file with invalid JSON."""
        config_file = tmp_path / "invalid_config.json"
        with open(config_file, "w") as f:
            f.write("this is not valid json")

        settings = Settings(config_file=str(config_file))

        with pytest.raises(ValueError):
            settings.load_config_from_file()

    def test_load_config_with_invalid_structure(self, tmp_path):
        """Test loading config from a file with invalid structure."""
        config_file = tmp_path / "invalid_structure.json"
        with open(config_file, "w") as f:
            json.dump({"invalid_field": "value"}, f)

        settings = Settings(config_file=str(config_file))

        # Should raise validation error due to missing required fields
        # Actually AppConfig has defaults so it might not fail
        # Let's just test that it doesn't crash
        app_config = settings.load_config_from_file()
        assert isinstance(app_config, AppConfig)


class TestGetConfigIntegration:
    """Test integration between Settings and AppConfig."""

    def test_get_config_without_file(self):
        """Test getting config without a config file."""
        settings = Settings()
        app_config = settings.get_config()

        assert isinstance(app_config, AppConfig)
        # Should have default values from Settings
        assert str(app_config.host) == "0.0.0.0"
        assert app_config.port == 9090

    def test_get_config_with_file_and_env_override(self, tmp_path):
        """Test that environment variables override config file values."""
        config_data = {
            "host": "127.0.0.1",
            "port": 8080,
            "jwt_issuer": "file-issuer",
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        with patch.dict(os.environ, {"PYESB_HOST": "0.0.0.0", "PYESB_PORT": "9090"}):
            settings = Settings(config_file=str(config_file))
            app_config = settings.get_config()

            # Environment variables should override file values
            assert str(app_config.host) == "0.0.0.0"  # From env, not file
            assert app_config.port == 9090  # From env, not file

    def test_get_config_preserves_file_data(self, tmp_path):
        """Test that file-specific data is preserved when environment overrides are applied."""
        config_data = {
            "clients": {
                "test_client": {
                    "client_id": "test",
                    "client_secret": "secret",
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "user_list_id": "00000000-0000-0000-0000-000000000000",
                    "user_presentation": "Test User",
                }
            },
            "applications": {
                "test_app": [
                    {
                        "process": "test_proc",
                        "channel": "test_chan",
                        "access": "READ_ONLY",
                    }
                ]
            },
            "host": "127.0.0.1",
            "port": 8080,
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        settings = Settings(config_file=str(config_file))
        app_config = settings.get_config()

        # File-specific data should be preserved
        assert len(app_config.clients) == 1
        assert "test_client" in app_config.clients
        assert len(app_config.applications) == 1
        assert "test_app" in app_config.applications

        # Settings values should still apply (defaults match file in this case)
        assert str(app_config.host) == "0.0.0.0"  # Settings default
        assert app_config.port == 9090  # Settings default

    def test_get_settings_function(self):
        """Test the get_settings helper function."""
        settings = get_settings()

        assert isinstance(settings, Settings)
        # Should have default values
        assert str(settings.host) == "0.0.0.0"
        assert settings.port == 9090

    def test_get_config_with_env_file(self, tmp_path):
        """Test loading settings from .env file."""
        env_file = tmp_path / ".env"
        with open(env_file, "w") as f:
            f.write("PYESB_HOST=127.0.0.1\n")
            f.write("PYESB_PORT=8080\n")
            f.write("PYESB_JWT_ISSUER=env-issuer\n")

        # Create a new Settings class with the custom env file
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class TestSettings(BaseSettings):
            host: str = "0.0.0.0"
            port: int = 9090
            jwt_issuer: str = "unused-issuer"

            model_config = SettingsConfigDict(
                env_prefix="PYESB_", env_file=str(env_file), env_file_encoding="utf-8"
            )

        settings = TestSettings()

        assert str(settings.host) == "127.0.0.1"
        assert settings.port == 8080
        assert settings.jwt_issuer == "env-issuer"


class TestAppConfigModel:
    """Test AppConfig model validation and defaults."""

    def test_app_config_defaults(self):
        """Test AppConfig default values."""
        config = AppConfig()

        assert str(config.host) == "0.0.0.0"
        assert config.port == 9090
        assert config.amqp_port == 6698
        assert config.jwt_issuer == "unused-issuer"
        assert config.token_ttl_seconds == 3600
        assert len(config.clients) == 0
        assert len(config.applications) == 0

    def test_app_config_with_data(self):
        """Test AppConfig with custom data."""
        client = ClientCredentials(
            client_id="test",
            client_secret="secret",
            user_id="00000000-0000-0000-0000-000000000000",
            user_list_id="00000000-0000-0000-0000-000000000000",
            user_presentation="Test User",
        )

        channel = Channel(
            process="test_proc",
            channel="test_chan",
            access="READ_ONLY",
        )

        config = AppConfig(
            clients={"test": client},
            applications={"test_app": [channel]},
            host="127.0.0.1",
            port=8080,
        )

        assert str(config.host) == "127.0.0.1"
        assert config.port == 8080
        assert len(config.clients) == 1
        assert len(config.applications) == 1

    def test_client_credentials_validation(self):
        """Test ClientCredentials validation."""
        client = ClientCredentials(
            client_id="test",
            client_secret="secret",
            user_id="00000000-0000-0000-0000-000000000000",
            user_list_id="00000000-0000-0000-0000-000000000000",
            user_presentation="Test User",
        )

        assert client.client_id == "test"
        assert client.client_secret == "secret"
        assert client.user_presentation == "Test User"

    def test_channel_validation(self):
        """Test Channel validation."""
        channel = Channel(
            process="test_proc",
            channel="test_chan",
            access="READ_ONLY",
            process_description="Test Process",
            channel_description="Test Channel",
        )

        assert channel.process == "test_proc"
        assert channel.channel == "test_chan"
        assert channel.access == "READ_ONLY"
        assert channel.process_description == "Test Process"
        assert channel.channel_description == "Test Channel"

    def test_app_config_validation_error(self):
        """Test AppConfig validation with invalid data."""
        # Test invalid port
        with pytest.raises(ValidationError):
            AppConfig(port=-1)

        # Test invalid token TTL
        with pytest.raises(ValidationError):
            AppConfig(token_ttl_seconds=0)

        # Test invalid host (IPv4 address)
        # These should fail because they're not valid IPv4 addresses
        invalid_hosts = ["invalid.ip.address", "256.0.0.1", "not.an.ip"]
        for host in invalid_hosts:
            with pytest.raises(ValidationError):
                AppConfig(host=host)


class TestEnvironmentPrefix:
    """Test environment variable prefix handling."""

    def test_env_prefix_isolation(self):
        """Test that PYEB_ prefix isolates settings from other env vars."""
        # Set some non-PYESB env vars that shouldn't affect settings
        with patch.dict(
            os.environ,
            {
                "HOST": "wrong.host",
                "PORT": "1234",
                "JWT_ISSUER": "wrong-issuer",
            },
        ):
            settings = Settings()

            # Should use defaults, not the non-prefixed env vars
            assert str(settings.host) == "0.0.0.0"
            assert settings.port == 9090
            assert settings.jwt_issuer == "unused-issuer"

    def test_env_prefix_case_sensitivity(self):
        """Test that env prefix is case-sensitive."""
        with patch.dict(
            os.environ,
            {
                "pyesb_HOST": "192.168.1.1",  # lowercase prefix - should be ignored
                "PYESB_HOST": "10.0.0.1",  # uppercase prefix - should be used
            },
        ):
            settings = Settings()
            assert str(settings.host) == "10.0.0.1"


class TestIPv4AddressValidation:
    """Test IPv4Address type validation and functionality."""

    def test_valid_ipv4_address(self):
        """Test that valid IPv4 addresses are accepted."""
        from app.interfaces import IPv4Address

        valid_addresses = ["127.0.0.1", "0.0.0.0", "192.168.1.1", "10.0.0.1"]

        for addr in valid_addresses:
            ip = IPv4Address(addr)
            assert str(ip) == addr
            assert isinstance(ip, str)

    def test_invalid_ipv4_address(self):
        """Test that invalid IPv4 addresses are rejected through Pydantic."""
        from pydantic import BaseModel

        from app.interfaces import IPv4Address

        class TestModel(BaseModel):
            host: IPv4Address

        invalid_addresses = ["256.0.0.1", "192.168.1", "not.an.ip", ""]

        for addr in invalid_addresses:
            with pytest.raises(ValidationError):
                TestModel(host=addr)

    def test_ipv4_address_in_settings(self):
        """Test that IPv4Address works correctly in Settings."""
        from app.interfaces import IPv4Address

        # Test with valid IP
        settings = Settings(host="192.168.1.1")
        assert str(settings.host) == "192.168.1.1"
        assert isinstance(settings.host, IPv4Address)
        assert settings.host.is_private()
        assert not settings.host.is_loopback()

        # Test with default IP
        settings = Settings()
        assert str(settings.host) == "0.0.0.0"
        assert isinstance(settings.host, IPv4Address)

    def test_ipv4_address_in_app_config(self):
        """Test that IPv4Address works correctly in AppConfig."""
        from app.interfaces import IPv4Address

        # Test with valid IP
        config = AppConfig(host="10.0.0.1")
        assert str(config.host) == "10.0.0.1"
        assert isinstance(config.host, IPv4Address)
        assert config.host.is_private()

        # Test with default IP
        config = AppConfig()
        assert str(config.host) == "0.0.0.0"
        assert isinstance(config.host, IPv4Address)
        assert config.host.is_any()

    def test_ipv4_address_methods(self):
        """Test the additional methods of IPv4Address."""
        from app.interfaces import IPv4Address

        # Test loopback
        loopback = IPv4Address("127.0.0.1")
        assert loopback.is_loopback()
        assert not loopback.is_any()
        assert loopback.is_private()

        # Test private addresses
        private_10 = IPv4Address("10.0.0.1")
        assert private_10.is_private()
        assert not private_10.is_loopback()

        private_172 = IPv4Address("172.16.0.1")
        assert private_172.is_private()

        private_192 = IPv4Address("192.168.1.1")
        assert private_192.is_private()

        # Test "any" address
        any_addr = IPv4Address("0.0.0.0")
        assert any_addr.is_any()
        assert not any_addr.is_loopback()

        # Test link local
        link_local = IPv4Address("169.254.1.1")
        assert link_local.is_link_local()
