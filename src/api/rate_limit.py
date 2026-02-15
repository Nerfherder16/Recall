"""
Rate limiter singleton for the API.

Separated from main.py to avoid circular imports when
route modules need to reference the limiter.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
)
