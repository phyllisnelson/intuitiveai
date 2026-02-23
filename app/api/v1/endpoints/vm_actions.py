"""VM action endpoints — sub-resource operations on a specific VM.

POST   /api/v1/vms/{vm_id}/actions      Power action      → 202 Accepted
PUT    /api/v1/vms/{vm_id}/resize       Resize            → 202 Accepted
POST   /api/v1/vms/{vm_id}/snapshots    Create snapshot   → 202 Accepted
GET    /api/v1/vms/{vm_id}/console      Console URL       → 200 OK
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Query, status

from app.api.deps import ReadAuthDep, ServiceDep, WriteAuthDep
from app.core.handlers import handle_domain_error
from app.schemas.common import APIResponse
from app.schemas.task import TaskResponse
from app.schemas.vm_actions import (
    ConsoleResponse,
    SnapshotCreateRequest,
    VMActionRequest,
    VMResizeRequest,
)

router = APIRouter(tags=["vms"])
log = structlog.get_logger(__name__)


@router.post(
    "/vms/{vm_id}/actions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[dict],
    summary="Perform a power action on a VM",
    responses={
        202: {"description": "Action accepted."},
        409: {"description": "Invalid state for the requested action."},
    },
)
async def vm_action(
    vm_id: str,
    payload: VMActionRequest,
    service: ServiceDep,
    _auth: WriteAuthDep,
) -> APIResponse[dict]:
    """Execute a power action (start / stop / reboot / suspend / resume)."""
    try:
        await service.perform_action(vm_id, payload)
    except Exception as exc:
        handle_domain_error(exc)

    log.info("api.vm.action", vm_id=vm_id, action=payload.action)
    return APIResponse(
        data={"vm_id": vm_id, "action": payload.action, "accepted": True},
        meta={"note": "State transition may take a few seconds."},
    )


@router.put(
    "/vms/{vm_id}/resize",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[TaskResponse],
    summary="Resize a VM to a different flavor",
)
async def resize_vm(
    vm_id: str,
    payload: VMResizeRequest,
    service: ServiceDep,
    _auth: WriteAuthDep,
) -> APIResponse[TaskResponse]:
    try:
        task = await service.resize_vm(vm_id, payload)
    except Exception as exc:
        handle_domain_error(exc)

    log.info(
        "api.vm.resize",
        vm_id=vm_id,
        flavor=payload.flavor_id,
        task_id=str(task.task_id),
    )
    return APIResponse(data=task)


@router.post(
    "/vms/{vm_id}/snapshots",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[TaskResponse],
    summary="Create a snapshot of a VM",
)
async def create_snapshot(
    vm_id: str,
    payload: SnapshotCreateRequest,
    service: ServiceDep,
    _auth: WriteAuthDep,
) -> APIResponse[TaskResponse]:
    try:
        _snap, task = await service.create_snapshot(vm_id, payload)
    except Exception as exc:
        handle_domain_error(exc)

    log.info(
        "api.vm.snapshot",
        vm_id=vm_id,
        name=payload.name,
        task_id=str(task.task_id),
    )
    return APIResponse(data=task)


@router.get(
    "/vms/{vm_id}/console",
    response_model=APIResponse[ConsoleResponse],
    summary="Get a time-limited console URL",
)
async def get_console(
    vm_id: str,
    service: ServiceDep,
    _auth: ReadAuthDep,
    console_type: Annotated[str, Query()] = "novnc",
) -> APIResponse[ConsoleResponse]:
    try:
        console = await service.get_console_url(vm_id, console_type)
    except Exception as exc:
        handle_domain_error(exc)
    return APIResponse(data=console)
