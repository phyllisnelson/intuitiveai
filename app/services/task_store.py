"""Async task store for tracking long-running operations.

RedisTaskStore is persistent, survives restarts, and works safely across
multiple workers.  Requires REDIS_URL to be set.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.schemas.enums import TaskStatus
from app.schemas.task import TaskResponse

_KEY_PREFIX = "task:"


class RedisTaskStore:
    """Redis-backed task store — survives restarts and works across workers.

    Keys are stored as  task:<task_id>  with a configurable TTL so the
    store self-cleans without an explicit purge job.

    Expects a redis.asyncio client created with decode_responses=True.
    """

    def __init__(self, redis: Any, ttl: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl

    async def create(
        self,
        operation: str,
        resource_id: str | None = None,
    ) -> TaskResponse:
        task_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        record = TaskResponse(
            task_id=uuid.UUID(task_id),
            status=TaskStatus.PENDING,
            operation=operation,
            resource_id=resource_id,
            created_at=now,
            updated_at=now,
        )
        await self._redis.set(
            f"{_KEY_PREFIX}{task_id}",
            record.model_dump_json(),
            ex=self._ttl,
        )
        return record

    async def update(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        resource_id: str | None = None,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        raw = await self._redis.get(f"{_KEY_PREFIX}{task_id}")
        if raw is None:
            return
        record = TaskResponse.model_validate_json(raw)
        record.status = status
        record.updated_at = datetime.now(UTC)
        if resource_id is not None:
            record.resource_id = resource_id
        if error is not None:
            record.error = error
        if result is not None:
            record.result = result
        await self._redis.set(
            f"{_KEY_PREFIX}{task_id}",
            record.model_dump_json(),
            ex=self._ttl,
        )

    async def get(self, task_id: str) -> TaskResponse | None:
        raw = await self._redis.get(f"{_KEY_PREFIX}{task_id}")
        if raw is None:
            return None
        return TaskResponse.model_validate_json(raw)

    async def list_all(self) -> list[TaskResponse]:
        keys = await self._redis.keys(f"{_KEY_PREFIX}*")
        if not keys:
            return []
        values = await self._redis.mget(*keys)
        return [TaskResponse.model_validate_json(v) for v in values if v is not None]
