"""OpenStack service facade.

Owns the connection lifecycle and routes public API calls to domain-specific
sub-clients.  The only non-trivial logic here is resolving the default network
ID from settings before delegating to ComputeClient.create_vm.

Adding a new OpenStack service area (e.g. Neutron) means creating a new
sub-client module and wiring it here, without touching existing clients.

Connection pooling: a single ``openstack.Connection`` object is created once
at startup and reused across requests.  openstacksdk handles thread-safety
internally.  Each blocking call is wrapped with ``asyncio.to_thread`` so the
FastAPI event loop is never blocked.
"""

import asyncio
from functools import partial

import openstack
import structlog
from arq.connections import ArqRedis

from app.core.config import Settings
from app.core.exceptions import OpenStackConnectionError, VMOperationError
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
from app.schemas.vms import VMCreate, VMResponse
from app.services._compute import POLL_TIMEOUT_SECONDS, ComputeClient
from app.services._image import ImageClient
from app.services.base import BaseOpenStackService
from app.services.task_store import RedisTaskStore

log = structlog.get_logger(__name__)


class OpenStackService(BaseOpenStackService):
    def __init__(
        self,
        settings: Settings,
        task_store: RedisTaskStore,
        arq_pool: ArqRedis | None = None,
    ) -> None:
        self._settings = settings
        self._conn: openstack.connection.Connection | None = None
        self._compute = ComputeClient(self._run, task_store, arq_pool)
        self._image = ImageClient(self._run)

    def _get_conn(self) -> openstack.connection.Connection:
        if self._conn is None:
            try:
                self._conn = openstack.connect(**self._settings.openstack_conn_kwargs)
                log.info(
                    "openstack.connected",
                    auth_url=self._settings.openstack_auth_url,
                )
            except Exception as exc:
                log.error("openstack.connect.failed", error=str(exc))
                raise OpenStackConnectionError(str(exc)) from exc
        return self._conn

    async def _run(self, func, *args, **kwargs):
        """Run a blocking SDK call in a thread pool."""
        conn = self._get_conn()
        try:
            return await asyncio.to_thread(partial(func, conn, *args, **kwargs))
        except OpenStackConnectionError:
            raise
        except openstack.exceptions.NotFoundException:
            raise
        except openstack.exceptions.ConflictException:
            raise
        except Exception as exc:
            log.error("openstack.operation.failed", error=str(exc))
            raise VMOperationError(str(exc)) from exc

    async def healthcheck(self) -> bool:
        try:
            conn = self._get_conn()
            await asyncio.to_thread(conn.authorize)
            return True
        except Exception:
            return False

    async def list_vms(
        self,
        status: str | None = None,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VMResponse], int]:
        return await self._compute.list_vms(
            status=status,
            name=name,
            limit=limit,
            offset=offset,
        )

    async def get_vm(self, vm_id: str) -> VMResponse:
        return await self._compute.get_vm(vm_id)

    async def create_vm(self, payload: VMCreate) -> tuple[str, TaskResponse]:
        network_id = payload.network_id or self._settings.openstack_default_network_id
        if not network_id:
            raise VMOperationError(
                "No network_id provided and OPENSTACK_DEFAULT_NETWORK_ID is not set.",
            )
        return await self._compute.create_vm(payload, network_id)

    async def delete_vm(self, vm_id: str) -> TaskResponse:
        return await self._compute.delete_vm(vm_id)

    async def perform_action(self, vm_id: str, request: VMActionRequest) -> None:
        await self._compute.perform_action(vm_id, request)

    async def resize_vm(self, vm_id: str, request: VMResizeRequest) -> TaskResponse:
        return await self._compute.resize_vm(vm_id, request)

    async def create_snapshot(
        self,
        vm_id: str,
        request: SnapshotCreateRequest,
    ) -> tuple[SnapshotResponse, TaskResponse]:
        return await self._compute.create_snapshot(vm_id, request)

    async def get_console_url(
        self,
        vm_id: str,
        console_type: str = "novnc",
    ) -> ConsoleResponse:
        return await self._compute.get_console_url(vm_id, console_type)

    async def list_flavors(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FlavorResponse], int]:
        return await self._compute.list_flavors(limit=limit, offset=offset)

    async def list_images(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImageResponse], int]:
        return await self._image.list_images(limit=limit, offset=offset)

    async def poll_until_active(
        self,
        vm_id: str,
        task_id: str,
        timeout: int = POLL_TIMEOUT_SECONDS,
    ) -> None:
        await self._compute.poll_until_active(vm_id, task_id, timeout)

    async def do_delete(self, vm_id: str, task_id: str) -> None:
        await self._compute.do_delete(vm_id, task_id)

    async def do_resize(self, vm_id: str, task_id: str, flavor_id: str) -> None:
        await self._compute.do_resize(vm_id, task_id, flavor_id)
