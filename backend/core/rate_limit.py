"""
core/rate_limit.py
------------------
PURPOSE:
    Provides the shared slowapi Limiter singleton.

    Keeping the limiter in its own module breaks the circular import that would
    occur if chat/router.py imported from main.py (which imports chat/router.py).

USAGE:
    from core.rate_limit import limiter

    # In main.py — attach to app:
    app.state.limiter = limiter

    # In a router — decorate an endpoint:
    @limiter.limit("20/minute")
    def my_endpoint(request: Request, ...):
        ...

    Note: The decorated endpoint MUST accept a `request: Request` parameter
    so slowapi can read the client IP for rate key tracking.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level singleton — import this everywhere, never instantiate again.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
