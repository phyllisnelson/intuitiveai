"""Tests for VM CRUD endpoints."""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.exceptions import OpenStackConnectionError
from tests.conftest import TEST_API_KEY
from tests.mocks.openstack import MockOpenStackService


class _FailingService(MockOpenStackService):
    async def create_vm(self, payload):
        raise OpenStackConnectionError()

    async def list_vms(self, **kwargs):
        raise OpenStackConnectionError()


@pytest.fixture
def failing_client(app, task_store) -> TestClient:
    app.dependency_overrides[deps.get_openstack_service] = lambda: _FailingService(
        task_store=task_store,
    )
    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as c:
        yield c
    app.dependency_overrides.pop(deps.get_openstack_service, None)


class VMsBase:
    base = "/api/v1/vms"


class TestList(VMsBase):
    def test_list_vms_returns_seeded_data(self, client):
        resp = client.get(self.base)
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["total"] >= 3
        assert len(body["data"]) >= 3

    def test_list_vms_filter_by_status(self, client):
        resp = client.get(self.base, params={"status": "ACTIVE"})
        assert resp.status_code == HTTPStatus.OK
        for vm in resp.json()["data"]:
            assert vm["status"] == "ACTIVE"

    def test_list_vms_filter_by_name(self, client):
        # Factory names follow the pattern "vm-NNNN".
        resp = client.get(self.base, params={"name": "vm-"})
        assert resp.status_code == HTTPStatus.OK
        assert len(resp.json()["data"]) >= 1
        for vm in resp.json()["data"]:
            assert "vm-" in vm["name"].lower()

    def test_list_vms_pagination(self, client):
        resp = client.get(self.base, params={"limit": 1, "offset": 0})
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["page_size"] == 1


class TestGet(VMsBase):
    def test_get_vm_seeded(self, client):
        vm_id = client.get(self.base).json()["data"][0]["id"]
        resp = client.get(f"{self.base}/{vm_id}")
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()["data"]
        assert body["id"] == vm_id
        assert body["name"]

    def test_get_vm_not_found(self, client):
        resp = client.get(f"{self.base}/nonexistent-vm-id")
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestCreate(VMsBase):
    def test_create_vm_returns_202(self, client):
        payload = {
            "name": "test-vm-01",
            "flavor_id": "m1.small",
            "image_id": "img-ubuntu-2204",
            "network_id": "test-network",
        }
        resp = client.post(self.base, json=payload)
        assert resp.status_code == HTTPStatus.ACCEPTED
        body = resp.json()
        assert "data" in body
        task = body["data"]
        assert task["operation"] == "create_vm"
        assert task["status"] in ("pending", "running", "success")
        assert "vm_id" in body["meta"]

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "name": "bad name with spaces",
                "flavor_id": "m1.small",
                "image_id": "img-ubuntu-2204",
            },
            {"name": "incomplete"},
        ],
    )
    def test_create_vm_invalid_payload_rejected(self, client, payload):
        resp = client.post(self.base, json=payload)
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestDelete(VMsBase):
    def test_delete_vm_returns_202(self, client):
        vm_id = client.get(self.base).json()["data"][-1]["id"]
        resp = client.delete(f"{self.base}/{vm_id}")
        assert resp.status_code == HTTPStatus.ACCEPTED
        assert resp.json()["data"]["operation"] == "delete_vm"

    def test_delete_vm_not_found(self, client):
        resp = client.delete(f"{self.base}/ghost-vm")
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestServiceErrors(VMsBase):
    def test_create_vm_service_error_returns_503(self, failing_client):
        payload = {
            "name": "test-vm",
            "flavor_id": "m1.small",
            "image_id": "img-ubuntu-2204",
        }
        resp = failing_client.post(self.base, json=payload)
        assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE

    def test_list_vms_service_error_returns_503(self, failing_client):
        resp = failing_client.get(self.base)
        assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
