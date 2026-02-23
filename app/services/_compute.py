"""Compute (Nova) sub-client — wraps openstacksdk compute operations.

Owns the full lifecycle of compute resources: SDK calls, task-store updates,
and arq job scheduling.  The facade only resolves settings-level concerns
(e.g. default network ID) before delegating here.
"""

import asyncio
from datetime import UTC, datetime

import openstack
import structlog
from arq.connections import ArqRedis

from app.core.exceptions import InvalidVMStateError, VMNotFoundError, VMOperationError
from app.schemas.enums import TaskStatus, VMAction, VMState
from app.schemas.flavor import FlavorResponse
from app.schemas.task import TaskResponse
from app.schemas.vm_actions import (
    ConsoleResponse,
    SnapshotCreateRequest,
    SnapshotResponse,
    VMActionRequest,
    VMResizeRequest,
)
from app.schemas.vms import AddressInfo, VMCreate, VMResponse
from app.services.task_store import RedisTaskStore

log = structlog.get_logger(__name__)

POLL_TIMEOUT_SECONDS = 300
_POLL_INTERVAL_SECONDS = 5
_RESIZE_CONFIRM_DELAY_SECONDS = 5

# Maps OpenStack server status strings to our VMState enum.
_OS_STATE_MAP: dict[str, VMState] = {
    "ACTIVE": VMState.ACTIVE,
    "SHUTOFF": VMState.SHUTOFF,
    "SUSPENDED": VMState.SUSPENDED,
    "BUILD": VMState.BUILDING,
    "BUILDING": VMState.BUILDING,
    "REBOOT": VMState.REBOOT,
    "HARD_REBOOT": VMState.REBOOT,
    "ERROR": VMState.ERROR,
    "DELETED": VMState.DELETED,
    "RESIZE": VMState.RESIZE,
    "VERIFY_RESIZE": VMState.VERIFY_RESIZE,
}


def _map_state(raw_status: str) -> VMState:
    return _OS_STATE_MAP.get(raw_status.upper(), VMState.UNKNOWN)


def _server_to_response(server) -> VMResponse:
    """Convert an openstacksdk Server resource to our VMResponse schema."""
    addresses: dict[str, list[AddressInfo]] = {}
    for net_name, addr_list in (server.addresses or {}).items():
        addresses[net_name] = [
            AddressInfo(
                version=a.get("version", 4),
                addr=a.get("addr", ""),
                type=a.get("OS-EXT-IPS:type"),
            )
            for a in addr_list
        ]

    flavor = server.flavor or {}
    image = server.image or {}

    return VMResponse(
        id=server.id,
        name=server.name,
        status=_map_state(server.status or "UNKNOWN"),
        flavor_id=flavor.get("id", ""),
        image_id=image.get("id") if isinstance(image, dict) else None,
        addresses=addresses,
        key_name=server.key_name,
        security_groups=[sg.get("name", "") for sg in (server.security_groups or [])],
        metadata=server.metadata or {},
        created_at=(
            datetime.fromisoformat(server.created_at)
            if server.created_at
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(server.updated_at) if server.updated_at else None
        ),
        host_id=server.host_id,
        availability_zone=getattr(server, "availability_zone", None),
    )


class ComputeClient:
    """Wraps Nova (compute) API calls and owns compute task orchestration."""

    def __init__(
        self,
        run,
        task_store: RedisTaskStore,
        arq_pool: ArqRedis | None,
    ) -> None:
        self._run = run
        self._task_store = task_store
        self._arq_pool = arq_pool

    async def list_vms(
        self,
        status: str | None = None,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VMResponse], int]:
        filters: dict = {}
        if status:
            filters["status"] = status.upper()
        if name:
            filters["name"] = name

        def _list(conn):
            return list(conn.compute.servers(**filters))

        servers = await self._run(_list)
        total = len(servers)
        return [_server_to_response(s) for s in servers[offset : offset + limit]], total

    async def get_vm(self, vm_id: str) -> VMResponse:
        def _get(conn):
            return conn.compute.get_server(vm_id)

        try:
            server = await self._run(_get)
        except openstack.exceptions.NotFoundException as exc:
            raise VMNotFoundError(vm_id) from exc
        return _server_to_response(server)

    async def get_console_url(
        self,
        vm_id: str,
        console_type: str = "novnc",
    ) -> ConsoleResponse:
        def _console(conn):
            return conn.compute.get_server_console_url(vm_id, console_type=console_type)

        result = await self._run(_console)
        console = result.get("console", {})
        return ConsoleResponse(
            type=console.get("type", console_type),
            url=console.get("url", ""),
        )

    async def list_flavors(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FlavorResponse], int]:
        def _flavors(conn):
            return list(conn.compute.flavors())

        raw = await self._run(_flavors)
        flavors = [
            FlavorResponse(
                id=f.id,
                name=f.name,
                vcpus=f.vcpus,
                ram_mb=f.ram,
                disk_gb=f.disk,
                is_public=getattr(f, "is_public", True),
            )
            for f in raw
        ]
        return flavors[offset : offset + limit], len(flavors)

    async def _enqueue_job(self, job_name: str, *args) -> None:
        if self._arq_pool is None:
            raise VMOperationError("arq pool is not configured")
        await self._arq_pool.enqueue_job(job_name, *args)

    async def create_vm(
        self,
        payload: VMCreate,
        network_id: str,
    ) -> tuple[str, TaskResponse]:
        def _create(conn):
            return conn.compute.create_server(
                name=payload.name,
                image_id=payload.image_id,
                flavor_id=payload.flavor_id,
                networks=[{"uuid": network_id}],
                key_name=payload.key_name,
                security_groups=[{"name": sg} for sg in payload.security_groups],
                user_data=payload.user_data,
                metadata=payload.metadata,
            )

        server = await self._run(_create)
        task = await self._task_store.create("create_vm", resource_id=server.id)
        await self._enqueue_job("poll_until_active", server.id, str(task.task_id))
        return server.id, task

    async def delete_vm(self, vm_id: str) -> TaskResponse:
        await self.get_vm(vm_id)
        task = await self._task_store.create("delete_vm", resource_id=vm_id)
        await self._enqueue_job("do_delete", vm_id, str(task.task_id))
        return task

    async def perform_action(self, vm_id: str, request: VMActionRequest) -> None:
        await self.get_vm(vm_id)
        action = request.action

        def _act(conn):
            match action:
                case VMAction.START:
                    conn.compute.start_server(vm_id)
                case VMAction.STOP:
                    conn.compute.stop_server(vm_id)
                case VMAction.REBOOT:
                    rtype = (request.reboot_type or "SOFT").upper()
                    conn.compute.reboot_server(vm_id, reboot_type=rtype)
                case VMAction.HARD_REBOOT:
                    conn.compute.reboot_server(vm_id, reboot_type="HARD")
                case VMAction.SUSPEND:
                    conn.compute.suspend_server(vm_id)
                case VMAction.RESUME:
                    conn.compute.resume_server(vm_id)

        try:
            await self._run(_act)
        except openstack.exceptions.ConflictException as exc:
            raise InvalidVMStateError(str(exc)) from exc

    async def resize_vm(self, vm_id: str, request: VMResizeRequest) -> TaskResponse:
        await self.get_vm(vm_id)
        task = await self._task_store.create("resize_vm", resource_id=vm_id)
        await self._enqueue_job(
            "do_resize",
            vm_id,
            str(task.task_id),
            request.flavor_id,
        )
        return task

    async def create_snapshot(
        self,
        vm_id: str,
        request: SnapshotCreateRequest,
    ) -> tuple[SnapshotResponse, TaskResponse]:
        await self.get_vm(vm_id)
        task = await self._task_store.create("create_snapshot", resource_id=vm_id)

        def _snap(conn):
            return conn.compute.create_server_image(vm_id, name=request.name)

        image = await self._run(_snap)
        snap = SnapshotResponse(
            id=image.id,
            name=image.name,
            status="saving",
            source_vm_id=vm_id,
            created_at=datetime.now(UTC),
        )
        await self._task_store.update(
            str(task.task_id),
            status=TaskStatus.SUCCESS,
            result={"snapshot_id": image.id},
        )
        return snap, task

    async def poll_until_active(
        self,
        vm_id: str,
        task_id: str,
        timeout: int = POLL_TIMEOUT_SECONDS,
    ) -> None:
        await self._task_store.update(task_id, status=TaskStatus.RUNNING)
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS
            try:
                vm = await self.get_vm(vm_id)
            except Exception:
                continue
            if vm.status == VMState.ACTIVE:
                await self._task_store.update(task_id, status=TaskStatus.SUCCESS)
                return
            if vm.status == VMState.ERROR:
                await self._task_store.update(
                    task_id,
                    status=TaskStatus.FAILED,
                    error="VM entered ERROR state.",
                )
                return
        await self._task_store.update(
            task_id,
            status=TaskStatus.FAILED,
            error="Timeout waiting for VM to become ACTIVE.",
        )

    async def do_delete(self, vm_id: str, task_id: str) -> None:
        await self._task_store.update(task_id, status=TaskStatus.RUNNING)
        try:

            def _delete(conn):
                conn.compute.delete_server(vm_id)

            await self._run(_delete)
            await self._task_store.update(task_id, status=TaskStatus.SUCCESS)
        except Exception as exc:
            await self._task_store.update(
                task_id,
                status=TaskStatus.FAILED,
                error=str(exc),
            )

    async def do_resize(self, vm_id: str, task_id: str, flavor_id: str) -> None:
        await self._task_store.update(task_id, status=TaskStatus.RUNNING)
        try:

            def _resize(conn):
                conn.compute.resize_server(vm_id, flavor_id)

            def _confirm(conn):
                conn.compute.confirm_server_resize(vm_id)

            await self._run(_resize)
            await asyncio.sleep(_RESIZE_CONFIRM_DELAY_SECONDS)
            await self._run(_confirm)
            await self._task_store.update(task_id, status=TaskStatus.SUCCESS)
        except Exception as exc:
            await self._task_store.update(
                task_id,
                status=TaskStatus.FAILED,
                error=str(exc),
            )
