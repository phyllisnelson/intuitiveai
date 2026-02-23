"""Flavor catalog endpoints.

GET /api/v1/flavors  — list all compute flavors available to the project.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ReadAuthDep, ServiceDep
from app.schemas.common import PaginatedResponse
from app.schemas.flavor import FlavorResponse

router = APIRouter(tags=["flavors"])


@router.get(
    "/flavors",
    response_model=PaginatedResponse[FlavorResponse],
    summary="List available compute flavors",
)
async def list_flavors(
    service: ServiceDep,
    _auth: ReadAuthDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[FlavorResponse]:
    """Return compute flavors visible to the current project.

    Flavors define the CPU / RAM / disk profile of a VM.
    """
    flavors, total = await service.list_flavors(limit=limit, offset=offset)
    return PaginatedResponse.from_page(
        data=flavors,
        total=total,
        limit=limit,
        offset=offset,
    )
