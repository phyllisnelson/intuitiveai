"""Tests for /api/v1/tasks."""

from http import HTTPStatus


class TestTasks:
    base = "/api/v1/tasks"
    vms_base = "/api/v1/vms"

    def test_task_lifecycle(self, client):
        # Create a VM to generate a task.
        payload = {
            "name": "task-test-vm",
            "flavor_id": "m1.small",
            "image_id": "img-ubuntu-2204",
            "network_id": "test-network",
        }
        create_resp = client.post(self.vms_base, json=payload)
        assert create_resp.status_code == HTTPStatus.ACCEPTED
        task_id = create_resp.json()["data"]["task_id"]

        # Poll task.
        task_resp = client.get(f"{self.base}/{task_id}")
        assert task_resp.status_code == HTTPStatus.OK
        task_data = task_resp.json()["data"]
        assert task_data["task_id"] == task_id
        assert task_data["operation"] == "create_vm"

    def test_task_not_found(self, client):
        resp = client.get(f"{self.base}/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == HTTPStatus.NOT_FOUND
