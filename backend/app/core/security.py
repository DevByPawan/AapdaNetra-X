"""AapdaNetra-X — Security, Authentication & Authorization Module

Phase 6.32: Implements configurable, server-side authentication and role-based access control (RBAC).
Provides dependencies for protecting decision state changes, simulations, administrative endpoints, and SSE streams.
"""

from typing import List, Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    user_id: str
    role: str  # "admin" | "responder" | "viewer"
    scopes: List[str] = []


# Built-in demonstration / test API token mapping
KNOWN_TOKENS = {
    "admin-token-secret-123": AuthenticatedUser(user_id="ADMIN-01", role="admin", scopes=["*"]),
    "responder-token-secret-456": AuthenticatedUser(user_id="RESP-01", role="responder", scopes=["decision:write", "simulation:write"]),
    "viewer-token-secret-789": AuthenticatedUser(user_id="VIEWER-01", role="viewer", scopes=["read"]),
}


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> AuthenticatedUser:
    """Extracts and verifies authentication credentials.

    Enforces server-side authorization while allowing development fallback when auth_enabled is False.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif x_api_key:
        token = x_api_key

    # 1. Configured API key matching
    if settings.api_key and token == settings.api_key:
        return AuthenticatedUser(user_id="API-KEY-CLIENT", role="responder", scopes=["*"])

    # 2. Known token mapping (permitted ONLY in development / test environments)
    is_prod = settings.environment.lower() == "production"
    if not is_prod and token in KNOWN_TOKENS:
        return KNOWN_TOKENS[token]

    # 3. Invalid credentials supplied
    if token is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. No credentials supplied
    is_prod = settings.environment.lower() == "production"
    if settings.auth_enabled or is_prod:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Development mode default user when no header is supplied
    return AuthenticatedUser(user_id="DEV-RESPONDER-01", role="responder", scopes=["*"])


def require_roles(allowed_roles: List[str]):
    """Returns a FastAPI dependency asserting that the authenticated user possesses an authorized role."""

    async def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed_roles and "*" not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires one of roles {allowed_roles}. Current role: '{user.role}'",
            )
        return user

    return role_checker
