import time

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)

# Supabase caches JWKS for 10 min; they recommend 20 min before revoking old keys.
# We refresh every 15 min so rotations propagate without rejecting valid tokens.
_JWKS_TTL = 900
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0


def _fetch_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    if time.monotonic() - _jwks_fetched_at > _JWKS_TTL:
        url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_fetched_at = time.monotonic()
    return _jwks_cache


def validate_token(token: str) -> dict:
    """Validate a Supabase-issued JWT and return its claims."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise _credentials_error

    kid = header.get("kid")
    jwks = _fetch_jwks()

    rsa_key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if rsa_key is None:
        raise _credentials_error

    try:
        return jwt.decode(
            token,
            rsa_key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
        )
    except JWTError:
        raise _credentials_error
