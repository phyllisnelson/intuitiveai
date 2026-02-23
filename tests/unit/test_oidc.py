from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.oidc import (
    Principal,
    _extract_roles,
    _introspect,
    get_current_user,
    require_read,
    require_write,
)
from app.core.config import Settings


def _settings(**kwargs) -> Settings:
    defaults = dict(
        keycloak_url="https://keycloak.example.com",
        keycloak_realm="test",
        keycloak_client_id="vm-api",
        keycloak_client_secret="secret",
        keycloak_reader_role="vm-reader",
        keycloak_operator_role="vm-operator",
        api_key="",
    )
    defaults.update(kwargs)
    return Settings(**defaults)


def _make_request(oidc_client=None) -> MagicMock:
    request = MagicMock()
    request.app.state.oidc_client = oidc_client
    return request


def _principal(auth_method: str = "oidc", roles: list[str] | None = None) -> Principal:
    return Principal(
        subject="u1",
        username="alice",
        roles=frozenset(roles or []),
        auth_method=auth_method,
    )


def _mock_response(claims: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = claims
    return resp


class TestExtractRoles:
    def test_extracts_realm_roles(self):
        claims = {"realm_access": {"roles": ["vm-reader", "offline_access"]}}
        assert _extract_roles(claims) == frozenset({"vm-reader", "offline_access"})

    def test_missing_realm_access_returns_empty(self):
        assert _extract_roles({}) == frozenset()

    def test_missing_roles_key_returns_empty(self):
        assert _extract_roles({"realm_access": {}}) == frozenset()


class TestIntrospect:
    @pytest.mark.asyncio
    async def test_active_token_returns_claims(self):
        settings = _settings()
        client = AsyncMock()
        client.post.return_value = _mock_response({"active": True, "sub": "user-123"})

        result = await _introspect("tok", settings, client)

        assert result == {"active": True, "sub": "user-123"}
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inactive_token_returns_none(self):
        settings = _settings()
        client = AsyncMock()
        client.post.return_value = _mock_response({"active": False})

        result = await _introspect("tok", settings, client)

        assert result is None

    @pytest.mark.asyncio
    async def test_connection_error_raises_503(self):
        settings = _settings()
        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("unreachable")

        with pytest.raises(HTTPException) as exc_info:
            await _introspect("tok", settings, client)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_http_exception_is_reraised(self):
        settings = _settings()
        client = AsyncMock()
        inner = HTTPException(status_code=502)
        resp = MagicMock()
        resp.raise_for_status.side_effect = inner
        client.post.return_value = resp

        with pytest.raises(HTTPException) as exc_info:
            await _introspect("tok", settings, client)
        assert exc_info.value is inner


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_bearer_returns_oidc_principal(self):
        settings = _settings()
        mock_client = AsyncMock()
        mock_client.post.return_value = _mock_response(
            {
                "active": True,
                "sub": "user-123",
                "preferred_username": "alice",
                "realm_access": {"roles": ["vm-reader"]},
            },
        )
        request = _make_request(oidc_client=mock_client)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        )

        principal = await get_current_user(
            request=request,
            settings=settings,
            bearer_credentials=credentials,
        )

        assert principal.auth_method == "oidc"
        assert principal.subject == "user-123"
        assert principal.username == "alice"
        assert "vm-reader" in principal.roles

    @pytest.mark.asyncio
    async def test_inactive_bearer_raises_401(self):
        settings = _settings()
        mock_client = AsyncMock()
        mock_client.post.return_value = _mock_response({"active": False})
        request = _make_request(oidc_client=mock_client)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bad-token",
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                settings=settings,
                bearer_credentials=credentials,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_returns_apikey_principal(self):
        settings = _settings(keycloak_url="", api_key="mysecret")
        request = _make_request()

        principal = await get_current_user(
            request=request,
            settings=settings,
            api_key_header="mysecret",
        )

        assert principal.auth_method == "apikey"
        assert "vm-reader" in principal.roles
        assert "vm-operator" in principal.roles

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_401(self):
        settings = _settings(keycloak_url="", api_key="mysecret")
        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                settings=settings,
                api_key_header="wrong",
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_401(self):
        settings = _settings(keycloak_url="", api_key="mysecret")
        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, settings=settings)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_auth_configured_raises_401(self):
        settings = _settings(keycloak_url="", api_key="")
        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, settings=settings)
        assert exc_info.value.status_code == 401


class TestRequireRead:
    @pytest.mark.asyncio
    async def test_apikey_passes(self):
        principal = _principal(auth_method="apikey")
        result = await require_read(principal=principal, settings=_settings())
        assert result is principal

    @pytest.mark.asyncio
    async def test_reader_role_passes(self):
        principal = _principal(auth_method="oidc", roles=["vm-reader"])
        result = await require_read(principal=principal, settings=_settings())
        assert result is principal

    @pytest.mark.asyncio
    async def test_operator_role_passes(self):
        principal = _principal(auth_method="oidc", roles=["vm-operator"])
        result = await require_read(principal=principal, settings=_settings())
        assert result is principal

    @pytest.mark.asyncio
    async def test_no_matching_role_raises_403(self):
        principal = _principal(auth_method="oidc", roles=["unrelated-role"])
        with pytest.raises(HTTPException) as exc_info:
            await require_read(principal=principal, settings=_settings())
        assert exc_info.value.status_code == 403


class TestRequireWrite:
    @pytest.mark.asyncio
    async def test_apikey_passes(self):
        principal = _principal(auth_method="apikey")
        result = await require_write(principal=principal, settings=_settings())
        assert result is principal

    @pytest.mark.asyncio
    async def test_operator_role_passes(self):
        principal = _principal(auth_method="oidc", roles=["vm-operator"])
        result = await require_write(principal=principal, settings=_settings())
        assert result is principal

    @pytest.mark.asyncio
    async def test_reader_only_raises_403(self):
        principal = _principal(auth_method="oidc", roles=["vm-reader"])
        with pytest.raises(HTTPException) as exc_info:
            await require_write(principal=principal, settings=_settings())
        assert exc_info.value.status_code == 403
