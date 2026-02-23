"""FastAPI dependency injection providers.

Import these in endpoint modules with ``Depends()``.
"""

from typing import Annotated

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Depends

from app.api.oidc import Principal, require_read, require_write
from app.core.config import Settings, get_settings
from app.services.base import BaseOpenStackService
from app.services.openstack_service import OpenStackService
from app.services.task_store import RedisTaskStore

log = structlog.get_logger(__name__)

# Module-level singletons — one instance per worker process.
_service_instance: BaseOpenStackService | None = None
_task_store_instance: RedisTaskStore | None = None
_arq_pool_instance: ArqRedis | None = None


def get_task_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedisTaskStore:
    """Return the RedisTaskStore singleton.

    Requires REDIS_URL to be configured; raises ValueError otherwise.
    Tests override this dependency via conftest.py.
    """
    global _task_store_instance
    if _task_store_instance is None:
        if not settings.redis_url:
            raise ValueError(
                "REDIS_URL must be configured. "
                "Set the REDIS_URL environment variable.",
            )
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        _task_store_instance = RedisTaskStore(client, ttl=settings.task_ttl_seconds)
        log.info("task_store.backend", backend="redis", url=settings.redis_url)
    return _task_store_instance


async def get_arq_pool(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ArqRedis | None:
    """Return the arq connection pool singleton, or None if REDIS_URL is unset.

    When available, the pool is passed to OpenStackService so background
    operations are enqueued in Redis rather than spawned as in-process tasks.
    Tests override this dependency via conftest.py (implicitly — it is not
    overridden, so it returns None because redis_url is unset in tests).
    """
    global _arq_pool_instance
    if _arq_pool_instance is None and settings.redis_url:
        _arq_pool_instance = await create_pool(
            RedisSettings.from_dsn(settings.redis_url),
        )
        log.info("arq.pool.created", redis_url=settings.redis_url)
    return _arq_pool_instance


async def get_openstack_service(
    settings: Annotated[Settings, Depends(get_settings)],
    task_store: Annotated[RedisTaskStore, Depends(get_task_store)],
    arq_pool: Annotated[ArqRedis | None, Depends(get_arq_pool)],
) -> BaseOpenStackService:
    """Return the OpenStackService singleton.

    Uses a module-level singleton so the connection is not re-established
    on every request.  Tests override this dependency via conftest.py.
    """
    global _service_instance
    if _service_instance is None:
        log.info(
            "service.backend",
            backend="openstack",
            auth_url=settings.openstack_auth_url,
        )
        _service_instance = OpenStackService(settings, task_store, arq_pool=arq_pool)
    return _service_instance


# Convenience type aliases for use in endpoint signatures.
ServiceDep = Annotated[BaseOpenStackService, Depends(get_openstack_service)]
TaskStoreDep = Annotated[RedisTaskStore, Depends(get_task_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReadAuthDep = Annotated[Principal, Depends(require_read)]
WriteAuthDep = Annotated[Principal, Depends(require_write)]
