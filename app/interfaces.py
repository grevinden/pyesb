"""Type definitions for 1C ESB Gateway interfaces.

This module provides typed interfaces for string-based values to improve
type safety and prevent invalid values through the codebase.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Literal

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema


class AMQPAddress(str):
    """AMQP address/queue name for message routing.

    Examples: 'Kanal1SНазначение', 'Kanal1SИсточник', 'test_channel'
    """

    pass


class ProcessID(str):
    """1C integration process identifier.

    Format: namespace::group::process_name
    Examples: 'rav::test::Основное::ПроцессИнтеграции1'
    """

    pass


class ClientID(str):
    """OAuth2 client identifier used in Basic auth and JWT aud claim.

    Examples: 'test', 'my_client'
    """

    pass


AccessMode = Literal["READ_ONLY", "WRITE_ONLY"]
"""AMQP access mode for a channel.
- READ_ONLY: Consumer (receives messages from 1C)
- WRITE_ONLY: Producer (sends messages to 1C)
"""


class UserID(str):
    """1C user identifier as UUID string.

    Examples: '22af67ef-d0bd-4861-a7ed-519068ee7d68'
    """

    pass


class UserListID(str):
    """1C user list identifier as UUID string.

    Examples: '099d11dd-c6d9-401d-8c63-991f21876067'
    """

    pass


class UserPresentation(str):
    """User display name for UI presentation.

    Examples: 'test', 'Ivan Ivanov'
    """

    pass


class AuthIdentityName(str):
    """Base64-encoded SHA256 hash of client_id for JWT auth-identity.name claim.

    Examples: 'kgQsv_tArk8mX6Nq16YepTX9nzcBSf8v4-Y18ZN2sM='
    """

    pass


AuthIdentityDomain = Literal["user_tokens"]
"""Authentication identity domain for JWT claims.
Currently only 'user_tokens' is supported.
"""


class IPv4Address(str):
    """IPv4 address representation.

    This class provides type safety and validation for IPv4 addresses.
    Examples: '127.0.0.1', '0.0.0.0', '192.168.1.1'
    """

    @classmethod
    def validate(cls, v, handler):
        """Validate that the value is a valid IPv4 address."""
        if isinstance(v, cls):
            return v
        if isinstance(v, ipaddress.IPv4Address):
            return cls(str(v))
        if isinstance(v, str):
            try:
                ipaddress.IPv4Address(v)
                return cls(v)
            except ValueError as e:
                raise ValueError(f"Invalid IPv4 address: {v}") from e
        raise ValueError(f"Invalid IPv4 address: {v}")

    def to_ip_object(self) -> ipaddress.IPv4Address:
        """Convert to Python's ipaddress.IPv4Address object."""
        return ipaddress.IPv4Address(str(self))

    def is_loopback(self) -> bool:
        """Check if the address is a loopback address."""
        return self.to_ip_object().is_loopback

    def is_private(self) -> bool:
        """Check if the address is in a private network range."""
        ip_obj = self.to_ip_object()
        return (
            ip_obj.is_private
            or ip_obj in ipaddress.IPv4Network("10.0.0.0/8")
            or ip_obj in ipaddress.IPv4Network("172.16.0.0/12")
            or ip_obj in ipaddress.IPv4Network("192.168.0.0/16")
        )

    def is_any(self) -> bool:
        """Check if the address is 'any' (0.0.0.0)."""
        return str(self) == "0.0.0.0"

    def is_link_local(self) -> bool:
        """Check if the address is link-local (169.254.0.0/16)."""
        ip_obj = self.to_ip_object()
        return ip_obj in ipaddress.IPv4Network("169.254.0.0/16")

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Generate Pydantic core schema for IPv4Address."""
        return core_schema.general_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        """Generate JSON schema for IPv4Address."""
        return {
            "type": "string",
            "format": "ipv4",
            "pattern": r"^(\d{1,3}\.){3}\d{1,3}$",
            "example": "127.0.0.1",
        }


class AMQPUrl(str):
    """AMQP connection URL.

    Format: amqp://host:port
    Examples: 'amqp://0.0.0.0:6698'
    """

    pass
