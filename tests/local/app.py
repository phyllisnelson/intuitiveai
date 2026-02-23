"""Local development entry point — injects the mock OpenStack service.

This module must NEVER be imported by production code.  It exists solely as
the uvicorn target for ``make local-run`` and ``make local-up``.

The production ``app/`` package has no knowledge of this file.  The mock is
wired in here via FastAPI's dependency_overrides so the rest of the stack
(middleware, exception handlers, OpenAPI docs) is identical to production.

Task store backend:
    REDIS_URL set   → real Redis (used by docker compose local stack)
    REDIS_URL unset → FakeRedis in-process (used by make local-run standalone)

Usage:
    uvicorn tests.local.app:app --reload --port 8000
    docker compose -f docker-compose.local.yml up --build
"""

import os

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api import deps
from app.main import create_app
from app.schemas.enums import VMState
from app.services.task_store import RedisTaskStore
from tests.mocks.factories import (
    FlavorResponseFactory,
    ImageResponseFactory,
    VMResponseFactory,
)
from tests.mocks.openstack import MockOpenStackService

_redis_url = os.environ["REDIS_URL"]
_redis_client = aioredis.from_url(_redis_url, decode_responses=True)

_task_store = RedisTaskStore(_redis_client, ttl=86400)


def _make_seed_data() -> dict:
    """Build factory_boy seed objects and return them grouped for the response."""
    flavors = FlavorResponseFactory.build_batch(4)
    images = ImageResponseFactory.build_batch(3)
    active_vms = [
        VMResponseFactory(status=VMState.ACTIVE),
        VMResponseFactory(status=VMState.ACTIVE),
    ]
    shutoff_vms = [VMResponseFactory(status=VMState.SHUTOFF)]
    return {
        "flavors": flavors,
        "images": images,
        "vms": active_vms + shutoff_vms,
        "active_vms": active_vms,
        "shutoff_vms": shutoff_vms,
    }


_seed = _make_seed_data()
_mock_service = MockOpenStackService(
    task_store=_task_store,
    vms=_seed["vms"],
    flavors=_seed["flavors"],
    images=_seed["images"],
)

app = create_app()
app.dependency_overrides[deps.get_openstack_service] = lambda: _mock_service
app.dependency_overrides[deps.get_task_store] = lambda: _task_store

_dev_router = APIRouter(prefix="/dev", tags=["dev"])


@_dev_router.post("/reset", include_in_schema=False)
async def reset_mock() -> JSONResponse:
    """Reset the mock to an empty state."""
    _mock_service.__init__(_task_store)
    return JSONResponse({"reset": True})


@_dev_router.post("/seed", include_in_schema=False)
async def seed_mock() -> JSONResponse:
    """Re-seed the mock with factory_boy data and return the new resource IDs."""
    seed = _make_seed_data()
    _mock_service.__init__(
        _task_store,
        vms=seed["vms"],
        flavors=seed["flavors"],
        images=seed["images"],
    )
    return JSONResponse(
        {
            "vms": {
                "active": [v.id for v in seed["active_vms"]],
                "shutoff": [v.id for v in seed["shutoff_vms"]],
            },
            "flavors": [f.id for f in seed["flavors"]],
            "images": [i.id for i in seed["images"]],
        },
    )


app.include_router(_dev_router)
