"""Discord integration package.

This package provides a minimal async-like webhook client implemented with
a background worker thread and helper functions to send embed payloads.
"""

from .client import client

__all__ = ["client"]