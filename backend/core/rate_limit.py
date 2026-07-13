"""
Shared per-IP rate limiter for public-facing endpoints.

A single Limiter instance is imported by main.py (registration) and by the
route modules (decoration) to avoid circular imports between them.

The enabled flag is read directly from the environment (same convention as
COOKIE_SECURE / ENVIRONMENT in core/auth.py) rather than through
Settings.rate_limit.enabled: backend/tests/conftest.py replaces
backend.core.config with a MagicMock stub for the whole test session, and an
un-configured MagicMock attribute is truthy — reading the flag through that
stub would silently enable throttling for the entire suite. A direct
os.getenv() read is immune to that and defaults to disabled, exactly what the
suite needs. Per-route thresholds (auth/upload/lookup) still come from
Settings.rate_limit — those are evaluated lazily per-request via callables
passed to @limiter.limit(...), so they only matter once enabled=True.

Set RATE_LIMIT_ENABLED=true in production (see core/config.py for the
threshold env vars: RATE_LIMIT_AUTH_PER_MINUTE / RATE_LIMIT_UPLOAD_PER_HOUR /
RATE_LIMIT_LOOKUP_PER_MINUTE).
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true",
)
