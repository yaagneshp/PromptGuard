import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided_key: str | None = Security(api_key_header)) -> None:
    # secrets.compare_digest avoids leaking key length/prefix via response-time
    # differences (a plain `!=` short-circuits on the first mismatched byte).
    if provided_key is None or not secrets.compare_digest(provided_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
