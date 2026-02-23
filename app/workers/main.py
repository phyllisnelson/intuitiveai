"""arq worker entry point.

Run with:
    arq app.workers.main.WorkerSettings

The worker connects to Redis, picks up enqueued jobs, and executes them
inside a long-lived asyncio event loop.  Each worker process holds one
``OpenStackService`` instance so the OpenStack SDK connection is reused
across jobs.

The ``arq_pool`` is deliberately NOT passed to ``OpenStackService`` here —
the worker itself *is* the job processor, so there is nothing to re-enqueue.
"""

import os

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.services.openstack_service import OpenStackService
from app.services.task_store import RedisTaskStore
from app.workers.tasks import (
    do_delete,
    do_resize,
    poll_until_active,
)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    task_store = RedisTaskStore(client, ttl=settings.task_ttl_seconds)
    ctx["svc"] = OpenStackService(settings, task_store)


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [
        poll_until_active,
        do_delete,
        do_resize,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
    )
