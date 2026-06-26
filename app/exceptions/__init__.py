"""Exception-related utilities."""

from __future__ import annotations

import sys


def exc_info() -> str:
    """Return current exception as ``"TypeName: message"`` string.

    Use inside an ``except`` block to get a compact one-liner
    suitable for logging or error models::

        try:
            ...
        except ValueError as e:
            log_error(exc_info())  # "ValueError: invalid literal ..."
    """
    exc = sys.exc_info()[1]
    return f"{type(exc).__name__}: {exc}" if exc else ""


__all__ = [
    "exc_info",
]
