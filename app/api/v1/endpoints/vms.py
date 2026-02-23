"""VM lifecycle endpoints — core CRUD.

POST   /api/v1/vms                      Create VM         → 202 Accepted
GET    /api/v1/vms                      List VMs          → 200 OK
GET    /api/v1/vms/{vm_id}              Get VM            → 200 OK
DELETE /api/v1/vms/{vm_id}             Delete VM         → 202 Accepted

Sub-resource operations (power actions, resize, snapshots, console) live in
``vm_actions.py`` to keep each file focused on a single concern.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Query, status

from app.api.deps import ReadAuthDep, ServiceDep, WriteAuthDep
from app.core.handlers import handle_domain_error
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.task import TaskResponse
from app.schemas.vms import VMCreate, VMResponse

router = APIRouter(tags=["vms"])
log = structlog.get_logger(__name__)


@router.post(
    "/vms",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[TaskResponse],
    summary="Create a new VM",
    responses={
        202: {"description": "VM creation scheduled; poll task_id for status."},
        422: {"description": "Validation error in request body."},
    },
)
async def create_vm(
    payload: VMCreate,
    service: ServiceDep,
    _auth: WriteAuthDep,
) -> APIResponse[TaskResponse]:
    try:
        vm_id, task = await service.create_vm(payload)
    except Exception as exc:
        handle_domain_error(exc)

    log.info("api.vm.create", vm_id=vm_id, task_id=str(task.task_id), name=payload.name)
    return APIResponse(data=task, meta={"vm_id": vm_id})


@router.get(
    "/vms",
    response_model=PaginatedResponse[VMResponse],
    summary="List VMs",
)
async def list_vms(
    service: ServiceDep,
    _auth: ReadAuthDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    name: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[VMResponse]:
    """Return a paginated list of VMs, optionally filtered by status or name."""
    try:
        vms, total = await service.list_vms(
            status=status_filter,
            name=name,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        handle_domain_error(exc)

    return PaginatedResponse.from_page(
        data=vms,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/vms/{vm_id}",
    response_model=APIResponse[VMResponse],
    summary="Get VM details",
)
async def get_vm(
    vm_id: str,
    service: ServiceDep,
    _auth: ReadAuthDep,
) -> APIResponse[VMResponse]:
    try:
        vm = await service.get_vm(vm_id)
    except Exception as exc:
        handle_domain_error(exc)
    return APIResponse(data=vm)


@router.delete(
    "/vms/{vm_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[TaskResponse],
    summary="Delete a VM",
)
async def delete_vm(
    vm_id: str,
    service: ServiceDep,
    _auth: WriteAuthDep,
) -> APIResponse[TaskResponse]:
    try:
        task = await service.delete_vm(vm_id)
    except Exception as exc:
        handle_domain_error(exc)

    log.info("api.vm.delete", vm_id=vm_id, task_id=str(task.task_id))
    return APIResponse(data=task)
