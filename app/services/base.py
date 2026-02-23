"""Abstract base class for the OpenStack service layer.

Both the real ``OpenStackService`` and the ``MockOpenStackService`` implement
this interface, allowing the FastAPI dependency injection to swap them
transparently via conftest.py overrides in tests.
"""

from abc import ABC, abstractmethod

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


class BaseOpenStackService(ABC):
    """All service implementations must honour this contract."""

    @abstractmethod
    async def list_vms(
        self,
        status: str | None = None,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VMResponse], int]:
        """Return (page, total_count) for VMs matching the given filters."""

    @abstractmethod
    async def get_vm(self, vm_id: str) -> VMResponse:
        """Return a single VM or raise ``VMNotFoundError``."""

    @abstractmethod
    async def create_vm(self, payload: VMCreate) -> tuple[str, TaskResponse]:
        """Kick off VM creation.

        Returns
        -------
        (vm_id, task)
            vm_id is a string UUID; task is the pending TaskResponse.
        """

    @abstractmethod
    async def delete_vm(self, vm_id: str) -> TaskResponse:
        """Schedule VM deletion.  Returns the pending task."""

    @abstractmethod
    async def perform_action(self, vm_id: str, request: VMActionRequest) -> None:
        """Execute a power action on the VM (start / stop / reboot …)."""

    @abstractmethod
    async def resize_vm(self, vm_id: str, request: VMResizeRequest) -> TaskResponse:
        """Resize VM to a new flavor.  Returns the pending task."""

    @abstractmethod
    async def create_snapshot(
        self,
        vm_id: str,
        request: SnapshotCreateRequest,
    ) -> tuple[SnapshotResponse, TaskResponse]:
        """Create a snapshot image.  Returns (snapshot, task)."""

    @abstractmethod
    async def get_console_url(
        self,
        vm_id: str,
        console_type: str = "novnc",
    ) -> ConsoleResponse:
        """Return a time-limited console URL."""

    @abstractmethod
    async def list_flavors(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FlavorResponse], int]:
        """Return (page, total_count) for flavors visible to the current project."""

    @abstractmethod
    async def list_images(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImageResponse], int]:
        """Return (page, total_count) for images visible to the current project."""

    async def healthcheck(self) -> bool:
        """Return True if the OpenStack endpoint is reachable."""
        return True
