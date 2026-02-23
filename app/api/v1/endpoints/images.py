"""Image catalog endpoints.

GET /api/v1/images  — list all Glance images available to the project.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ReadAuthDep, ServiceDep
from app.schemas.common import PaginatedResponse
from app.schemas.image import ImageResponse

router = APIRouter(tags=["images"])


@router.get(
    "/images",
    response_model=PaginatedResponse[ImageResponse],
    summary="List available OS images",
)
async def list_images(
    service: ServiceDep,
    _auth: ReadAuthDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[ImageResponse]:
    """Return OS images (from OpenStack Glance) visible to the project.

    These IDs are used in the ``image_id`` field of the VM create request.
    """
    images, total = await service.list_images(limit=limit, offset=offset)
    return PaginatedResponse.from_page(
        data=images,
        total=total,
        limit=limit,
        offset=offset,
    )
