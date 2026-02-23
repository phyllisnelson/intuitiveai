"""v1 API router — aggregates all endpoint sub-routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    flavors,
    images,
    tasks,
    vm_actions,
    vms,
)

router = APIRouter(prefix="/api/v1")

router.include_router(vms.router)
router.include_router(vm_actions.router)
router.include_router(flavors.router)
router.include_router(images.router)
router.include_router(tasks.router)
