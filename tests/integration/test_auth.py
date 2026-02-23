from http import HTTPStatus

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.oidc import Principal, get_current_user
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.task_store import RedisTaskStore
from tests.mocks.openstack import MockOpenStackService


@pytest.fixture
def authed_client():
    task_store = RedisTaskStore(
        fakeredis.aioredis.FakeRedis(decode_responses=True),
        ttl=60,
    )
    app = create_app()
    app.dependency_overrides[deps.get_openstack_service] = lambda: MockOpenStackService(
        task_store=task_store,
    )
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    with TestClient(app) as c:
        yield c


def _oidc_client(app, roles: list[str], username: str = "alice") -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: Principal(
        subject="u1",
        username=username,
        roles=frozenset(roles),
        auth_method="oidc",
    )
    return TestClient(app)


class TestApiKey:
    base = "/api/v1/vms"

    def test_valid_api_key_is_accepted(self, authed_client):
        resp = authed_client.get(self.base, headers={"X-API-Key": "secret"})
        assert resp.status_code == HTTPStatus.OK

    def test_invalid_api_key_returns_401(self, authed_client):
        resp = authed_client.get(self.base, headers={"X-API-Key": "wrong"})
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    def test_missing_api_key_returns_401(self, authed_client):
        resp = authed_client.get(self.base)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


class TestOidcRbac:
    base = "/api/v1/vms"

    @pytest.mark.parametrize("roles", [["vm-reader"], ["vm-operator"]])
    def test_can_list_vms(self, app, roles):
        with _oidc_client(app, roles=roles) as c:
            resp = c.get(self.base)
        assert resp.status_code == HTTPStatus.OK

    def test_no_role_cannot_list_vms(self, app):
        with _oidc_client(app, roles=[]) as c:
            resp = c.get(self.base)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("roles", [["vm-reader"], []])
    def test_cannot_create_vm(self, app, roles):
        payload = {"name": "t", "flavor_id": "f", "image_id": "i"}
        with _oidc_client(app, roles=roles) as c:
            resp = c.post(self.base, json=payload)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_operator_can_create_vm(self, app):
        payload = {
            "name": "test",
            "flavor_id": "m1.small",
            "image_id": "img-ubuntu-2204",
        }
        with _oidc_client(app, roles=["vm-operator"]) as c:
            resp = c.post(self.base, json=payload)
        assert resp.status_code == HTTPStatus.ACCEPTED
