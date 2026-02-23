"""Unit tests for the ComputeClient sub-client (_compute.py).

Covers state mapping, server serialisation, all VM CRUD operations,
background task workers, and the console/snapshot/flavor helpers.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import openstack
import pytest

from app.core.exceptions import InvalidVMStateError, VMNotFoundError, VMOperationError
from app.schemas.enums import TaskStatus, VMAction, VMState
from app.schemas.vm_actions import (
    SnapshotCreateRequest,
    VMActionRequest,
    VMResizeRequest,
)
from app.services._compute import _map_state, _server_to_response
from tests.mocks.factories import (
    FlavorStubFactory,
    ServerStubFactory,
    TaskResponseFactory,
    VMResponseFactory,
)


class TestMapState:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ACTIVE", VMState.ACTIVE),
            ("SHUTOFF", VMState.SHUTOFF),
            ("BUILD", VMState.BUILDING),
            ("BUILDING", VMState.BUILDING),
            ("REBOOT", VMState.REBOOT),
            ("HARD_REBOOT", VMState.REBOOT),
            ("ERROR", VMState.ERROR),
            ("DELETED", VMState.DELETED),
            ("RESIZE", VMState.RESIZE),
            ("VERIFY_RESIZE", VMState.VERIFY_RESIZE),
            ("SUSPENDED", VMState.SUSPENDED),
            ("active", VMState.ACTIVE),  # case-insensitive
            ("WHATEVER", VMState.UNKNOWN),  # unknown → UNKNOWN
        ],
    )
    def test_maps_state(self, raw, expected):
        assert _map_state(raw) == expected


class TestServerToResponse:
    def test_basic_conversion(self):
        vm = _server_to_response(ServerStubFactory())
        assert vm.id == "vm-001"
        assert vm.name == "test-vm"
        assert vm.status == VMState.ACTIVE
        assert vm.flavor_id == "small"
        assert vm.image_id == "img-001"
        assert vm.key_name == "my-key"
        assert vm.security_groups == ["default"]

    def test_created_at_from_string(self):
        vm = _server_to_response(ServerStubFactory(created_at="2024-06-01T12:00:00"))
        assert vm.created_at == datetime.fromisoformat("2024-06-01T12:00:00")

    def test_created_at_defaults_when_none(self):
        vm = _server_to_response(ServerStubFactory(created_at=None))
        assert vm.created_at is not None

    def test_updated_at_from_string(self):
        vm = _server_to_response(ServerStubFactory(updated_at="2024-06-02T00:00:00"))
        assert vm.updated_at == datetime.fromisoformat("2024-06-02T00:00:00")

    def test_image_none_when_not_dict(self):
        vm = _server_to_response(ServerStubFactory(image=""))
        assert vm.image_id is None

    def test_empty_addresses(self):
        s = ServerStubFactory()
        s.addresses = {}
        vm = _server_to_response(s)
        assert vm.addresses == {}

    def test_no_security_groups(self):
        s = ServerStubFactory()
        s.security_groups = None
        vm = _server_to_response(s)
        assert vm.security_groups == []


class TestListVMs:
    @pytest.mark.asyncio
    async def test_returns_all_vms(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.servers.return_value = [ServerStubFactory()]
        with patch("openstack.connect", return_value=mock_conn):
            vms, total = await svc.list_vms()
        assert total == 1
        assert vms[0].id == "vm-001"

    @pytest.mark.asyncio
    async def test_status_filter_uppercased(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.servers.return_value = []
        with patch("openstack.connect", return_value=mock_conn):
            await svc.list_vms(status="active")
        mock_conn.compute.servers.assert_called_once_with(status="ACTIVE")

    @pytest.mark.asyncio
    async def test_name_filter_passed_through(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.servers.return_value = []
        with patch("openstack.connect", return_value=mock_conn):
            await svc.list_vms(name="web")
        mock_conn.compute.servers.assert_called_once_with(name="web")

    @pytest.mark.asyncio
    async def test_pagination_slices_result(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.servers.return_value = [
            ServerStubFactory(id=f"vm-{i:03d}") for i in range(5)
        ]
        with patch("openstack.connect", return_value=mock_conn):
            vms, total = await svc.list_vms(limit=2, offset=1)
        assert total == 5
        assert len(vms) == 2
        assert vms[0].id == "vm-001"


class TestGetVM:
    @pytest.mark.asyncio
    async def test_returns_vm(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory(id="vm-abc")
        with patch("openstack.connect", return_value=mock_conn):
            vm = await svc.get_vm("vm-abc")
        assert vm.id == "vm-abc"

    @pytest.mark.parametrize(
        "side_effect,exc_type",
        [
            (openstack.exceptions.NotFoundException(), VMNotFoundError),
            (Exception("502 Bad Gateway"), VMOperationError),
        ],
    )
    @pytest.mark.asyncio
    async def test_error_mapping(self, make_service, side_effect, exc_type):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.side_effect = side_effect
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(exc_type):
                await svc.get_vm("vm-test")


class TestDeleteVM:
    @pytest.mark.asyncio
    async def test_enqueues_job_and_returns_task_id(self, make_service):
        arq_pool = AsyncMock()
        svc, store = make_service(arq_pool=arq_pool)
        mock_task = TaskResponseFactory()
        store.create.return_value = mock_task
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        with patch("openstack.connect", return_value=mock_conn):
            task = await svc.delete_vm("vm-001")
        assert task is mock_task
        arq_pool.enqueue_job.assert_awaited_once_with(
            "do_delete",
            "vm-001",
            str(mock_task.task_id),
        )

    @pytest.mark.asyncio
    async def test_not_found_raises(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.side_effect = (
            openstack.exceptions.NotFoundException()
        )
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(VMNotFoundError):
                await svc.delete_vm("vm-missing")

    @pytest.mark.asyncio
    async def test_no_arq_pool_raises(self, make_service):
        svc, _ = make_service()  # arq_pool=None
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(VMOperationError, match="arq pool"):
                await svc.delete_vm("vm-001")


class TestDoDelete:
    @pytest.mark.asyncio
    async def test_success_updates_task(self, make_service):
        svc, store = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.delete_server.return_value = None
        with patch("openstack.connect", return_value=mock_conn):
            await svc.do_delete("vm-001", "task-001")
        store.update.assert_any_call("task-001", status=TaskStatus.RUNNING)
        store.update.assert_called_with("task-001", status=TaskStatus.SUCCESS)
        mock_conn.compute.delete_server.assert_called_once_with("vm-001")

    @pytest.mark.asyncio
    async def test_failure_marks_task_failed(self, make_service):
        svc, store = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.delete_server.side_effect = Exception("delete failed")
        with patch("openstack.connect", return_value=mock_conn):
            await svc.do_delete("vm-001", "task-001")
        final_call = store.update.call_args
        assert final_call.kwargs["status"] == TaskStatus.FAILED
        assert "delete failed" in final_call.kwargs["error"]


class TestPollUntilActive:
    @pytest.mark.asyncio
    async def test_marks_success_when_active(self, make_service):
        svc, store = make_service()
        with patch.object(
            svc._compute,
            "get_vm",
            return_value=VMResponseFactory(status=VMState.ACTIVE),
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.poll_until_active("vm-001", "task-001", timeout=10)
        store.update.assert_any_call("task-001", status=TaskStatus.RUNNING)
        store.update.assert_called_with("task-001", status=TaskStatus.SUCCESS)

    @pytest.mark.asyncio
    async def test_marks_failed_when_error_state(self, make_service):
        svc, store = make_service()
        with patch.object(
            svc._compute,
            "get_vm",
            return_value=VMResponseFactory(status=VMState.ERROR),
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.poll_until_active("vm-001", "task-001", timeout=10)
        store.update.assert_called_with(
            "task-001",
            status=TaskStatus.FAILED,
            error="VM entered ERROR state.",
        )

    @pytest.mark.asyncio
    async def test_marks_failed_on_timeout(self, make_service):
        svc, store = make_service()
        with patch.object(
            svc._compute,
            "get_vm",
            return_value=VMResponseFactory(status=VMState.BUILDING),
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.poll_until_active("vm-001", "task-001", timeout=4)
        store.update.assert_called_with(
            "task-001",
            status=TaskStatus.FAILED,
            error="Timeout waiting for VM to become ACTIVE.",
        )

    @pytest.mark.asyncio
    async def test_get_vm_exception_is_swallowed(self, make_service):
        svc, store = make_service()
        call_count = 0

        async def flaky_get_vm(vm_id):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("transient error")
            return VMResponseFactory(status=VMState.ACTIVE)

        with patch.object(svc._compute, "get_vm", side_effect=flaky_get_vm):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.poll_until_active("vm-001", "task-001", timeout=10)
        store.update.assert_called_with("task-001", status=TaskStatus.SUCCESS)


class TestPerformAction:
    async def _run_action(self, make_service, action_value, reboot_type=None):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        for attr in (
            "start_server",
            "stop_server",
            "reboot_server",
            "suspend_server",
            "resume_server",
        ):
            getattr(mock_conn.compute, attr).return_value = None
        request = VMActionRequest(action=VMAction(action_value))
        if reboot_type:
            request.reboot_type = reboot_type
        with patch("openstack.connect", return_value=mock_conn):
            await svc.perform_action("vm-001", request)
        return mock_conn

    @pytest.mark.parametrize(
        "action,method",
        [
            ("start", "start_server"),
            ("stop", "stop_server"),
            ("suspend", "suspend_server"),
            ("resume", "resume_server"),
        ],
    )
    @pytest.mark.asyncio
    async def test_simple_action(self, make_service, action, method):
        conn = await self._run_action(make_service, action)
        getattr(conn.compute, method).assert_called_once()

    @pytest.mark.asyncio
    async def test_reboot_soft(self, make_service):
        conn = await self._run_action(make_service, "reboot", reboot_type="SOFT")
        conn.compute.reboot_server.assert_called_once_with("vm-001", reboot_type="SOFT")

    @pytest.mark.asyncio
    async def test_hard_reboot(self, make_service):
        conn = await self._run_action(make_service, "hard_reboot")
        conn.compute.reboot_server.assert_called_once_with("vm-001", reboot_type="HARD")

    @pytest.mark.asyncio
    async def test_invalid_state_error_raised(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        mock_conn.compute.start_server.side_effect = (
            openstack.exceptions.ConflictException()
        )
        request = VMActionRequest(action=VMAction.START)
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(InvalidVMStateError):
                await svc.perform_action("vm-001", request)

    @pytest.mark.asyncio
    async def test_non_state_operation_error_propagates(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        mock_conn.compute.stop_server.side_effect = Exception("quota exceeded")
        request = VMActionRequest(action=VMAction.STOP)
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(VMOperationError):
                await svc.perform_action("vm-001", request)


class TestResizeVM:
    @pytest.mark.asyncio
    async def test_no_arq_pool_raises(self, make_service):
        svc, _ = make_service()  # arq_pool=None
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        request = VMResizeRequest(flavor_id="large")
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(VMOperationError, match="arq pool"):
                await svc.resize_vm("vm-001", request)

    @pytest.mark.asyncio
    async def test_enqueues_job_and_returns_task_id(self, make_service):
        arq_pool = AsyncMock()
        svc, store = make_service(arq_pool=arq_pool)
        mock_task = TaskResponseFactory()
        store.create.return_value = mock_task
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        request = VMResizeRequest(flavor_id="large")
        with patch("openstack.connect", return_value=mock_conn):
            task = await svc.resize_vm("vm-001", request)
        assert task is mock_task
        arq_pool.enqueue_job.assert_awaited_once_with(
            "do_resize",
            "vm-001",
            str(mock_task.task_id),
            "large",
        )


class TestDoResize:
    @pytest.mark.asyncio
    async def test_success_updates_task(self, make_service):
        svc, store = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.resize_server.return_value = None
        mock_conn.compute.confirm_server_resize.return_value = None
        with patch("openstack.connect", return_value=mock_conn):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.do_resize("vm-001", "task-001", "medium")
        store.update.assert_any_call("task-001", status=TaskStatus.RUNNING)
        store.update.assert_called_with("task-001", status=TaskStatus.SUCCESS)
        mock_conn.compute.resize_server.assert_called_once_with("vm-001", "medium")

    @pytest.mark.asyncio
    async def test_failure_marks_task_failed(self, make_service):
        svc, store = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.resize_server.side_effect = Exception("flavor not found")
        with patch("openstack.connect", return_value=mock_conn):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await svc.do_resize("vm-001", "task-001", "bad-flavor")
        final_call = store.update.call_args
        assert final_call.kwargs["status"] == TaskStatus.FAILED
        assert "flavor not found" in final_call.kwargs["error"]


class TestCreateSnapshot:
    @pytest.mark.asyncio
    async def test_returns_snapshot_and_task_id(self, make_service):
        svc, store = make_service()
        mock_task = TaskResponseFactory()
        store.create.return_value = mock_task
        mock_image = MagicMock()
        mock_image.id = "snap-001"
        mock_image.name = "my-snap"
        mock_conn = MagicMock()
        mock_conn.compute.get_server.return_value = ServerStubFactory()
        mock_conn.compute.create_server_image.return_value = mock_image
        request = SnapshotCreateRequest(name="my-snap")
        with patch("openstack.connect", return_value=mock_conn):
            snap, task = await svc.create_snapshot("vm-001", request)
        assert snap.id == "snap-001"
        assert task is mock_task
        store.update.assert_called_with(
            str(mock_task.task_id),
            status=TaskStatus.SUCCESS,
            result={"snapshot_id": "snap-001"},
        )


class TestGetConsoleUrl:
    @pytest.mark.asyncio
    async def test_returns_console_response(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.get_server_console_url.return_value = {
            "console": {"type": "novnc", "url": "https://console.example.com/vnc"},
        }
        with patch("openstack.connect", return_value=mock_conn):
            console = await svc.get_console_url("vm-001")
        assert console.url == "https://console.example.com/vnc"
        assert console.type == "novnc"


class TestListFlavors:
    @pytest.mark.asyncio
    async def test_returns_paginated_flavors(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.flavors.return_value = [
            FlavorStubFactory(id="small", name="m1.small", vcpus=1, ram=2048, disk=20),
        ]
        with patch("openstack.connect", return_value=mock_conn):
            flavors, total = await svc.list_flavors(limit=10, offset=0)
        assert total == 1
        assert flavors[0].id == "small"

    @pytest.mark.asyncio
    async def test_pagination(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.compute.flavors.return_value = [
            FlavorStubFactory(
                id=f"f{i}",
                name=f"flavor-{i}",
                vcpus=i + 1,
                ram=1024,
                disk=10,
            )
            for i in range(5)
        ]
        with patch("openstack.connect", return_value=mock_conn):
            flavors, total = await svc.list_flavors(limit=2, offset=2)
        assert total == 5
        assert len(flavors) == 2
        assert flavors[0].id == "f2"
