"""Keycloak OIDC authentication via token introspection + X-API-Key fallback.

Auth priority (first match wins):
  1. Authorization: Bearer <token>  — Keycloak introspection (requires KEYCLOAK_URL)
  2. X-API-Key: <key>               — static key check (when API_KEY is set)

At least one of KEYCLOAK_URL or API_KEY must be configured; 401 is returned
on every request if neither is set.

RBAC:
  require_read  — vm-reader OR vm-operator role (or valid API key)
  require_write — vm-operator role only        (or valid API key)
"""

from dataclasses import dataclass
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

log = structlog.get_logger(__name__)


@dataclass
class Principal:
    subject: str  # Keycloak "sub" claim or "apikey"
    username: str  # "preferred_username" from Keycloak, or auth method name
    roles: frozenset[str]
    auth_method: str  # "oidc" | "apikey"


async def _introspect(
    token: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> dict | None:
    """POST to Keycloak's token introspection endpoint.

    Returns the claims dict when the token is active, or None when inactive.
    Raises HTTP 503 if the Keycloak endpoint is unreachable.
    """
    url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/token/introspect"
    )
    try:
        resp = await client.post(
            url,
            data={"token": token},
            auth=(settings.keycloak_client_id, settings.keycloak_client_secret),
        )
        resp.raise_for_status()
        data = resp.json()
        return data if data.get("active") else None
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("oidc.introspect.error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC provider unavailable.",
        )


def _extract_roles(claims: dict) -> frozenset[str]:
    """Extract realm-level roles from introspection response claims."""
    return frozenset(claims.get("realm_access", {}).get("roles", []))


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ] = None,
    api_key_header: Annotated[str | None, Depends(_api_key_scheme)] = None,
) -> Principal:
    """Primary auth dependency — resolves the caller to a Principal.

    Tries Bearer (OIDC) first, then X-API-Key.  Raises 401 if neither
    KEYCLOAK_URL nor API_KEY is configured — authentication is always required.
    """
    if settings.keycloak_url and bearer_credentials is not None:
        token = bearer_credentials.credentials
        claims = await _introspect(token, settings, request.app.state.oidc_client)
        if claims is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        roles = _extract_roles(claims)
        log.info(
            "auth.oidc",
            sub=claims.get("sub"),
            username=claims.get("preferred_username"),
        )
        return Principal(
            subject=claims.get("sub", ""),
            username=claims.get("preferred_username", ""),
            roles=roles,
            auth_method="oidc",
        )

    if settings.api_key:
        if api_key_header is not None and api_key_header == settings.api_key:
            return Principal(
                subject="apikey",
                username="apikey",
                roles=frozenset(
                    {settings.keycloak_reader_role, settings.keycloak_operator_role},
                ),
                auth_method="apikey",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid credentials.",
            headers={"WWW-Authenticate": "Bearer, ApiKey"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Configure KEYCLOAK_URL or API_KEY.",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


async def require_read(
    principal: Annotated[Principal, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Allow callers with vm-reader OR vm-operator role (or valid API key)."""
    if principal.auth_method == "apikey":
        return principal
    allowed = {settings.keycloak_reader_role, settings.keycloak_operator_role}
    if not (principal.roles & allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Required role: {settings.keycloak_reader_role}"
                f" or {settings.keycloak_operator_role}."
            ),
        )
    return principal


async def require_write(
    principal: Annotated[Principal, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Allow callers with vm-operator role only (or valid API key)."""
    if principal.auth_method == "apikey":
        return principal
    if settings.keycloak_operator_role not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required role: {settings.keycloak_operator_role}.",
        )
    return principal
