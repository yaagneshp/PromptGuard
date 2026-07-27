import logging
import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from .config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = logging.getLogger("promptguard.auth")


def require_api_key(request: Request, provided_key: str | None = Security(api_key_header)) -> None:
    # secrets.compare_digest avoids leaking key length/prefix via response-time
    # differences (a plain `!=` short-circuits on the first mismatched byte).
    if provided_key is None or not secrets.compare_digest(provided_key, settings.api_key):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Rejected request with invalid API key from %s", client_host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
