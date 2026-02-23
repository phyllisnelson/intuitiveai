"""Tests for VM action endpoints — power actions, resize, snapshots, console."""

from http import HTTPStatus

import pytest


class VMActionsBase:
    base = "/api/v1/vms"


class TestActions(VMActionsBase):
    @pytest.mark.parametrize(
        "status,action",
        [
            ("ACTIVE", "stop"),
            ("SHUTOFF", "start"),
        ],
    )
    def test_action_accepted(self, client, status, action):
        vms = client.get(self.base, params={"status": status}).json()["data"]
        assert vms, f"No {status} VMs available."
        vm_id = vms[0]["id"]

        resp = client.post(f"{self.base}/{vm_id}/actions", json={"action": action})
        assert resp.status_code == HTTPStatus.ACCEPTED
        assert resp.json()["data"]["accepted"] is True

    def test_action_invalid_state(self, client):
        # Stop a SHUTOFF vm — should fail with 409.
        vms = client.get(self.base, params={"status": "SHUTOFF"}).json()["data"]
        assert vms
        vm_id = vms[0]["id"]

        resp = client.post(f"{self.base}/{vm_id}/actions", json={"action": "stop"})
        assert resp.status_code == HTTPStatus.CONFLICT

    def test_action_vm_not_found(self, client):
        resp = client.post(f"{self.base}/ghost/actions", json={"action": "start"})
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestResize(VMActionsBase):
    def test_resize_returns_202(self, client):
        vms = client.get(self.base, params={"status": "ACTIVE"}).json()["data"]
        vm_id = vms[0]["id"]
        flavor_id = client.get("/api/v1/flavors").json()["data"][0]["id"]

        resp = client.put(
            f"{self.base}/{vm_id}/resize",
            json={"flavor_id": flavor_id},
        )
        assert resp.status_code == HTTPStatus.ACCEPTED
        assert resp.json()["data"]["operation"] == "resize_vm"

    def test_resize_unknown_flavor(self, client):
        vms = client.get(self.base, params={"status": "ACTIVE"}).json()["data"]
        vm_id = vms[0]["id"]

        resp = client.put(
            f"{self.base}/{vm_id}/resize",
            json={"flavor_id": "nonexistent"},
        )
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestSnapshots(VMActionsBase):
    def test_create_snapshot_returns_202(self, client):
        vm_id = client.get(self.base).json()["data"][0]["id"]

        resp = client.post(
            f"{self.base}/{vm_id}/snapshots",
            json={"name": "test-snap-001"},
        )
        assert resp.status_code == HTTPStatus.ACCEPTED
        assert resp.json()["data"]["operation"] == "create_snapshot"

    def test_create_snapshot_vm_not_found(self, client):
        resp = client.post(
            f"{self.base}/ghost-vm/snapshots",
            json={"name": "test-snap-ghost"},
        )
        assert resp.status_code == HTTPStatus.NOT_FOUND


class TestConsole(VMActionsBase):
    def test_get_console_active_vm(self, client):
        vms = client.get(self.base, params={"status": "ACTIVE"}).json()["data"]
        vm_id = vms[0]["id"]

        resp = client.get(f"{self.base}/{vm_id}/console")
        assert resp.status_code == HTTPStatus.OK
        console = resp.json()["data"]
        assert "url" in console
        assert "http" in console["url"]

    def test_get_console_shutoff_vm_fails(self, client):
        vms = client.get(self.base, params={"status": "SHUTOFF"}).json()["data"]
        if not vms:
            pytest.skip("No SHUTOFF VMs available.")
        vm_id = vms[0]["id"]

        resp = client.get(f"{self.base}/{vm_id}/console")
        assert resp.status_code == HTTPStatus.CONFLICT
