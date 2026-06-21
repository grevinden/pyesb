"""Authentication utilities."""

import base64
import binascii
from typing import Optional, Tuple


def parse_basic_auth(auth_header: str) -> Optional[Tuple[str, str]]:
    """Parse Basic authentication header.

    Args:
        auth_header: Authentication header string (e.g., "Basic dXNlcjpwYXNz")

    Returns:
        Tuple of (username, password) if valid Basic auth header, None otherwise
    """
    if not auth_header or not auth_header.startswith("Basic "):
        return None

    try:
        # Extract base64 encoded credentials
        encoded_credentials = auth_header[6:]  # Remove "Basic " prefix
        decoded_bytes = base64.b64decode(encoded_credentials)
        decoded_str = decoded_bytes.decode("utf-8")

        # Split username and password by first colon
        if ":" in decoded_str:
            username, password = decoded_str.split(":", 1)
            return (username, password)
        else:
            # No colon found - treat entire string as username with empty password
            return (decoded_str, "")

    except (binascii.Error, UnicodeDecodeError):
        return None
