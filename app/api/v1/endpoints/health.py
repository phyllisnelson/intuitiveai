"""Health and readiness endpoints.

GET /health  — liveness probe  (always 200 if the process is running)
GET /ready   — readiness probe (200 only when the backend is reachable)
"""

from fastapi import APIRouter

from app.api.deps import ServiceDep, SettingsDep
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    """Always returns 200 while the process is alive.

    Suitable for Kubernetes liveness probes and load-balancer health checks.
    """
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        region=settings.openstack_region_name,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(service: ServiceDep, settings: SettingsDep) -> ReadinessResponse:
    """Returns 200 only when the OpenStack backend is reachable.

    Suitable for Kubernetes readiness probes — traffic is only routed once
    the pod is actually ready to serve requests.
    """
    ok = await service.healthcheck()
    return ReadinessResponse(
        ready=ok,
        region=settings.openstack_region_name,
        detail=None if ok else "OpenStack endpoint unreachable.",
    )
