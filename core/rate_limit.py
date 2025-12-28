"""Rate limiting configuration."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)
