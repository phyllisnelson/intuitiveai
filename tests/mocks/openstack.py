"""In-memory mock OpenStack service — for tests only.

Not imported by any production code path.  Injected exclusively via
conftest.py dependency overrides.

State machine:
    create  → BUILDING ──(~2 s)──► ACTIVE
    stop    → ACTIVE   ──(~1 s)──► SHUTOFF
    start   → SHUTOFF  ──(~1 s)──► ACTIVE
    reboot  → ACTIVE   ──(~1 s)──► ACTIVE
    suspend → ACTIVE   ──(~0.5 s)► SUSPENDED
    resume  → SUSPENDED──(~0.5 s)► ACTIVE
    resize  → ACTIVE   ──(~2 s)──► ACTIVE  (new flavor)
    delete  → any      ──(~1 s)──► (removed)
"""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.core.exceptions import (
    FlavorNotFoundError,
    InvalidVMStateError,
    VMNotFoundError,
)
from app.schemas.enums import TaskStatus, VMAction, VMState
from app.schemas.flavor import FlavorResponse
from app.schemas.image import ImageResponse
from app.schemas.task import TaskResponse
from app.schemas.vm_actions import (
    ConsoleResponse,
    SnapshotCreateRequest,
    SnapshotResponse,
    VMActionRequest,
    VMResizeRequest,
)
from app.schemas.vms import AddressInfo, VMCreate, VMResponse
from app.services.base import BaseOpenStackService
from app.services.task_store import RedisTaskStore

log = structlog.get_logger(__name__)


_ALLOWED_ACTIONS: dict[VMAction, set[VMState]] = {
    VMAction.START: {VMState.SHUTOFF},
    VMAction.STOP: {VMState.ACTIVE, VMState.SUSPENDED},
    VMAction.REBOOT: {VMState.ACTIVE},
    VMAction.HARD_REBOOT: {VMState.ACTIVE, VMState.ERROR, VMState.SHUTOFF},
    VMAction.SUSPEND: {VMState.ACTIVE},
    VMAction.RESUME: {VMState.SUSPENDED},
}

_ACTION_TARGET: dict[VMAction, VMState] = {
    VMAction.START: VMState.ACTIVE,
    VMAction.STOP: VMState.SHUTOFF,
    VMAction.REBOOT: VMState.ACTIVE,
    VMAction.HARD_REBOOT: VMState.ACTIVE,
    VMAction.SUSPEND: VMState.SUSPENDED,
    VMAction.RESUME: VMState.ACTIVE,
}


class MockOpenStackService(BaseOpenStackService):
    """Pure asyncio mock — for tests only, never imported by production code."""

    def __init__(
        self,
        task_store: RedisTaskStore,
        vms: list[VMResponse] | None = None,
        flavors: list[FlavorResponse] | None = None,
        images: list[ImageResponse] | None = None,
    ) -> None:
        self._task_store = task_store
        self._snapshots: dict[str, SnapshotResponse] = {}
        self._flavors: list[FlavorResponse] = list(flavors or [])
        self._images: list[ImageResponse] = list(images or [])
        self._flavor_map: dict[str, FlavorResponse] = {f.id: f for f in self._flavors}
        self._image_map: dict[str, ImageResponse] = {i.id: i for i in self._images}
        self._vms: dict[str, dict] = {}
        for vm in vms or []:
            self._vms[vm.id] = self._vm_to_dict(vm)

    @staticmethod
    def _vm_to_dict(vm: VMResponse) -> dict:
        """Convert a VMResponse schema to the internal raw-dict format."""
        net = next(iter(vm.addresses), "default-network")
        addr_list = vm.addresses.get(net, [])
        ip = addr_list[0].addr if addr_list else "192.168.0.1"
        return {
            "id": vm.id,
            "name": vm.name,
            "status": vm.status,
            "flavor_id": vm.flavor_id,
            "image_id": vm.image_id,
            "network": net,
            "ip": ip,
            "key_name": vm.key_name,
            "security_groups": list(vm.security_groups),
            "metadata": dict(vm.metadata),
            "created_at": vm.created_at,
            "updated_at": vm.updated_at,
            "availability_zone": vm.availability_zone,
        }

    def _make_vm(self, raw: dict) -> VMResponse:
        """Build a VMResponse from an internal raw dict."""
        flavor = self._flavor_map.get(raw["flavor_id"])
        image = self._image_map.get(raw.get("image_id", ""))
        net = raw.get("network", "default-network")
        ip = raw.get("ip", "192.168.0.1")
        return VMResponse(
            id=raw["id"],
            name=raw["name"],
            status=raw["status"],
            flavor_id=raw["flavor_id"],
            flavor_name=flavor.name if flavor else None,
            image_id=raw.get("image_id"),
            image_name=image.name if image else None,
            addresses={net: [AddressInfo(version=4, addr=ip, type="fixed")]},
            key_name=raw.get("key_name"),
            security_groups=raw.get("security_groups", ["default"]),
            metadata=raw.get("metadata", {}),
            created_at=raw.get("created_at", datetime.now(UTC)),
            updated_at=raw.get("updated_at"),
            availability_zone=raw.get("availability_zone", "nova"),
        )

    def _get_raw(self, vm_id: str) -> dict:
        vm = self._vms.get(vm_id)
        if vm is None:
            raise VMNotFoundError(f"VM '{vm_id}' not found.")
        return vm

    async def _transition(
        self,
        vm_id: str,
        intermediate: VMState,
        final: VMState,
        delay: float,
        task_id: str,
    ) -> None:
        await self._task_store.update(task_id, status=TaskStatus.RUNNING)
        if vm_id in self._vms:
            self._vms[vm_id]["status"] = intermediate
            self._vms[vm_id]["updated_at"] = datetime.now(UTC)
        await asyncio.sleep(delay)
        if vm_id in self._vms:
            self._vms[vm_id]["status"] = final
            self._vms[vm_id]["updated_at"] = datetime.now(UTC)
        await self._task_store.update(
            task_id,
            status=TaskStatus.SUCCESS,
            resource_id=vm_id,
        )

    async def list_vms(
        self,
        status: str | None = None,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VMResponse], int]:
        vms = [v for v in self._vms.values() if v["status"] != VMState.DELETED]
        if status:
            vms = [v for v in vms if v["status"].lower() == status.lower()]
        if name:
            vms = [v for v in vms if name.lower() in v["name"].lower()]
        total = len(vms)
        return [self._make_vm(v) for v in vms[offset : offset + limit]], total

    async def get_vm(self, vm_id: str) -> VMResponse:
        raw = self._get_raw(vm_id)
        if raw["status"] == VMState.DELETED:
            raise VMNotFoundError(f"VM '{vm_id}' has been deleted.")
        return self._make_vm(raw)

    async def create_vm(self, payload: VMCreate) -> tuple[str, TaskResponse]:
        vm_id = f"vm-{uuid.uuid4()}"
        task = await self._task_store.create("create_vm", resource_id=vm_id)
        now = datetime.now(UTC)
        self._vms[vm_id] = {
            "id": vm_id,
            "name": payload.name,
            "status": VMState.BUILDING,
            "flavor_id": payload.flavor_id,
            "image_id": payload.image_id,
            "network": payload.network_id or "default-network",
            "ip": ".".join(str(uuid.uuid4().int % 254) for _ in range(4)),
            "key_name": payload.key_name,
            "security_groups": payload.security_groups,
            "metadata": payload.metadata,
            "created_at": now,
            "updated_at": None,
            "availability_zone": "nova",
        }
        asyncio.create_task(
            self._transition(
                vm_id,
                VMState.BUILDING,
                VMState.ACTIVE,
                2.0,
                str(task.task_id),
            ),
        )
        return vm_id, task

    async def delete_vm(self, vm_id: str) -> TaskResponse:
        raw = self._get_raw(vm_id)
        task = await self._task_store.create("delete_vm", resource_id=vm_id)
        raw["status"] = VMState.DELETED
        task_id = str(task.task_id)

        async def _do_delete() -> None:
            await self._task_store.update(task_id, status=TaskStatus.RUNNING)
            await asyncio.sleep(1.0)
            self._vms.pop(vm_id, None)
            await self._task_store.update(task_id, status=TaskStatus.SUCCESS)

        asyncio.create_task(_do_delete())
        return task

    async def perform_action(self, vm_id: str, request: VMActionRequest) -> None:
        raw = self._get_raw(vm_id)
        current = VMState(raw["status"])
        allowed = _ALLOWED_ACTIONS.get(request.action, set())
        if current not in allowed:
            raise InvalidVMStateError(
                f"Cannot perform '{request.action}' on VM in state '{current}'.",
            )
        target = _ACTION_TARGET[request.action]
        task = await self._task_store.create(
            f"action_{request.action}",
            resource_id=vm_id,
        )
        intermediate = VMState.REBOOT if "reboot" in request.action else current
        asyncio.create_task(
            self._transition(vm_id, intermediate, target, 1.0, str(task.task_id)),
        )

    async def resize_vm(self, vm_id: str, request: VMResizeRequest) -> TaskResponse:
        raw = self._get_raw(vm_id)
        if raw["status"] not in (VMState.ACTIVE, VMState.SHUTOFF):
            raise InvalidVMStateError("VM must be ACTIVE or SHUTOFF to resize.")
        if request.flavor_id not in self._flavor_map:
            raise FlavorNotFoundError(f"Flavor '{request.flavor_id}' not found.")
        task = await self._task_store.create("resize_vm", resource_id=vm_id)
        task_id = str(task.task_id)
        original_status = VMState(raw["status"])

        async def _do_resize() -> None:
            await self._task_store.update(task_id, status=TaskStatus.RUNNING)
            raw["status"] = VMState.RESIZE
            raw["updated_at"] = datetime.now(UTC)
            await asyncio.sleep(2.0)
            raw["flavor_id"] = request.flavor_id
            raw["status"] = original_status
            raw["updated_at"] = datetime.now(UTC)
            await self._task_store.update(task_id, status=TaskStatus.SUCCESS)

        asyncio.create_task(_do_resize())
        return task

    async def create_snapshot(
        self,
        vm_id: str,
        request: SnapshotCreateRequest,
    ) -> tuple[SnapshotResponse, TaskResponse]:
        self._get_raw(vm_id)
        task = await self._task_store.create("create_snapshot", resource_id=vm_id)
        task_id = str(task.task_id)
        snap_id = f"snap-{uuid.uuid4()}"
        snap = SnapshotResponse(
            id=snap_id,
            name=request.name,
            status="saving",
            source_vm_id=vm_id,
            created_at=datetime.now(UTC),
        )
        self._snapshots[snap_id] = snap

        async def _do_snapshot() -> None:
            await self._task_store.update(task_id, status=TaskStatus.RUNNING)
            await asyncio.sleep(3.0)
            self._snapshots[snap_id].status = "active"
            await self._task_store.update(
                task_id,
                status=TaskStatus.SUCCESS,
                result={"snapshot_id": snap_id},
            )

        asyncio.create_task(_do_snapshot())
        return snap, task

    async def get_console_url(
        self,
        vm_id: str,
        console_type: str = "novnc",
    ) -> ConsoleResponse:
        raw = self._get_raw(vm_id)
        if raw["status"] != VMState.ACTIVE:
            raise InvalidVMStateError("Console is only available for ACTIVE VMs.")
        return ConsoleResponse(
            type=console_type,
            url=(
                "https://openstack.example.internal"
                f"/vnc_auto.html?token={uuid.uuid4()}"
            ),
        )

    async def list_flavors(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FlavorResponse], int]:
        flavors = self._flavors
        return flavors[offset : offset + limit], len(flavors)

    async def list_images(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImageResponse], int]:
        images = self._images
        return images[offset : offset + limit], len(images)
