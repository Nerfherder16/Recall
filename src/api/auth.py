"""
Authentication dependency — resolves Bearer token to User identity.
"""

import secrets

import structlog
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core import User, get_settings
from src.storage import get_postgres_store

logger = structlog.get_logger()
settings = get_settings()

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> User | None:
    """Validate Bearer token and resolve to User identity.

    Returns:
        None        — auth disabled (dev mode)
        User(id=0)  — authenticated via RECALL_API_KEY (system/admin)
        User(id=N)  — authenticated via per-user key from users table
    """
    if not settings.api_key:
        return None  # Auth disabled — dev mode

    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing API key")

    token = credentials.credentials

    # Check against master admin key first (constant-time)
    if secrets.compare_digest(token, settings.api_key):
        return User(id=0, username="system", display_name="System", is_admin=True)

    # Look up in users table
    try:
        pg = await get_postgres_store()
        user_data = await pg.get_user_by_api_key(token)
        if user_data:
            user = User(
                id=user_data["id"],
                username=user_data["username"],
                display_name=user_data["display_name"],
                is_admin=user_data["is_admin"],
            )
            # Touch last_active_at (fire-and-forget)
            await pg.update_user_last_active(user.id)
            return user
    except Exception as e:
        logger.warning("user_lookup_error", error=str(e))

    raise HTTPException(status_code=401, detail="Invalid API key")
