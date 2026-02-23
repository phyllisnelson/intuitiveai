"""Unit tests for the OpenStackService facade.

Covers connection lifecycle (_get_conn, _run), healthcheck, and the one
facade-level VM concern: network_id resolution during create_vm.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import openstack
import pytest

from app.core.exceptions import OpenStackConnectionError, VMOperationError
from app.schemas.vms import VMCreate
from tests.mocks.factories import TaskResponseFactory


class TestGetConn:
    def test_connects_lazily_on_first_call(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        with patch("openstack.connect", return_value=mock_conn) as mock_connect:
            conn = svc._get_conn()
        assert conn is mock_conn
        mock_connect.assert_called_once()

    def test_reuses_existing_connection(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        with patch("openstack.connect", return_value=mock_conn):
            assert svc._get_conn() is svc._get_conn()

    def test_connect_failure_raises_connection_error(self, make_service):
        svc, _ = make_service()
        with patch("openstack.connect", side_effect=Exception("timeout")):
            with pytest.raises(OpenStackConnectionError):
                svc._get_conn()


class TestRun:
    @pytest.mark.asyncio
    async def test_calls_function_with_conn(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        captured = {}

        def _fn(conn):
            captured["conn"] = conn
            return "result"

        with patch("openstack.connect", return_value=mock_conn):
            result = await svc._run(_fn)

        assert result == "result"
        assert captured["conn"] is mock_conn

    @pytest.mark.asyncio
    async def test_openstack_connection_error_passes_through(self, make_service):
        svc, _ = make_service()

        def _fn(conn):
            raise OpenStackConnectionError("down")

        with patch("openstack.connect", return_value=MagicMock()):
            with pytest.raises(OpenStackConnectionError):
                await svc._run(_fn)

    @pytest.mark.asyncio
    async def test_other_exceptions_become_vm_operation_error(self, make_service):
        svc, _ = make_service()

        def _fn(conn):
            raise RuntimeError("boom")

        with patch("openstack.connect", return_value=MagicMock()):
            with pytest.raises(VMOperationError):
                await svc._run(_fn)

    @pytest.mark.asyncio
    async def test_not_found_exception_passes_through(self, make_service):
        svc, _ = make_service()

        def _fn(conn):
            raise openstack.exceptions.NotFoundException()

        with patch("openstack.connect", return_value=MagicMock()):
            with pytest.raises(openstack.exceptions.NotFoundException):
                await svc._run(_fn)

    @pytest.mark.asyncio
    async def test_conflict_exception_passes_through(self, make_service):
        svc, _ = make_service()

        def _fn(conn):
            raise openstack.exceptions.ConflictException()

        with patch("openstack.connect", return_value=MagicMock()):
            with pytest.raises(openstack.exceptions.ConflictException):
                await svc._run(_fn)


class TestCreateVM:
    @pytest.mark.asyncio
    async def test_creates_vm_and_enqueues_poll(self, make_service):
        arq_pool = AsyncMock()
        svc, store = make_service(arq_pool=arq_pool)
        mock_task = TaskResponseFactory()
        store.create.return_value = mock_task
        mock_conn = MagicMock()
        mock_conn.compute.create_server.return_value = MagicMock(id="vm-new")
        payload = VMCreate(
            name="new-vm",
            image_id="img-001",
            flavor_id="small",
            network_id="net-001",
        )
        with patch("openstack.connect", return_value=mock_conn):
            vm_id, task = await svc.create_vm(payload)
        assert vm_id == "vm-new"
        assert task is mock_task
        arq_pool.enqueue_job.assert_awaited_once_with(
            "poll_until_active",
            "vm-new",
            str(mock_task.task_id),
        )

    @pytest.mark.asyncio
    async def test_no_arq_pool_raises_operation_error(self, make_service):
        svc, _ = make_service()  # arq_pool=None
        mock_conn = MagicMock()
        mock_conn.compute.create_server.return_value = MagicMock(id="vm-new")
        payload = VMCreate(
            name="new-vm",
            image_id="img-001",
            flavor_id="small",
            network_id="net-001",
        )
        with patch("openstack.connect", return_value=mock_conn):
            with pytest.raises(VMOperationError, match="arq pool"):
                await svc.create_vm(payload)

    @pytest.mark.asyncio
    async def test_no_network_raises_operation_error(self, make_service):
        svc, _ = make_service()
        payload = VMCreate(
            name="new-vm",
            image_id="img-001",
            flavor_id="small",
            network_id=None,
        )
        with patch("openstack.connect", return_value=MagicMock()):
            with pytest.raises(VMOperationError, match="network_id"):
                await svc.create_vm(payload)

    @pytest.mark.asyncio
    async def test_uses_payload_network_id(self, make_service):
        arq_pool = AsyncMock()
        svc, store = make_service(arq_pool=arq_pool)
        mock_conn = MagicMock()
        mock_conn.compute.create_server.return_value = MagicMock(id="vm-net")
        payload = VMCreate(
            name="new-vm",
            image_id="img-001",
            flavor_id="small",
            network_id="net-custom",
        )
        with patch("openstack.connect", return_value=mock_conn):
            await svc.create_vm(payload)
        assert mock_conn.compute.create_server.call_args.kwargs["networks"] == [
            {"uuid": "net-custom"},
        ]


class TestHealthcheck:
    @pytest.mark.asyncio
    async def test_returns_true_when_reachable(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.authorize.return_value = None
        with patch("openstack.connect", return_value=mock_conn):
            result = await svc.healthcheck()
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, make_service):
        svc, _ = make_service()
        with patch("openstack.connect", side_effect=Exception("unreachable")):
            result = await svc.healthcheck()
        assert result is False
