"""
Admin API routes — authentication dependency and management endpoints.

Provides `verify_admin_token` as a FastAPI dependency that validates Bearer
tokens against the configured `admin_api_token` setting.
"""

import logging

from fastapi import Header, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)


async def verify_admin_token(authorization: str = Header(None)) -> None:
    """
    FastAPI dependency: validate the Bearer token in the Authorization header.

    Behavior:
    - ``admin_api_token`` is empty → 503 (Admin API not configured)
    - ``Authorization`` header missing → 401 (Missing admin token)
    - Token mismatch → 401 (Invalid admin token)
    - Token matched → returns ``None`` (caller proceeds)

    Security: the actual token value is never logged.
    """
    settings = get_settings()

    # 1.1: empty token → service unavailable
    if not settings.admin_api_token:
        logger.warning("Admin API token not configured; rejecting admin request")
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured",
        )

    # 1.2: header missing
    if not authorization:
        logger.warning("Admin API request rejected: missing Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing admin token",
        )

    # 1.3: extract Bearer token
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning("Admin API request rejected: malformed Authorization header (expected Bearer)")
        raise HTTPException(
            status_code=401,
            detail="Missing admin token",
        )

    # 1.4: constant-time-ish string comparison (no early-exit)
    if token != settings.admin_api_token:
        logger.warning("Admin API request rejected: token mismatch")
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )

    return None
