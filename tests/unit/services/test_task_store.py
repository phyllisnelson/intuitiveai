"""Unit tests for app.services.task_store."""

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.schemas.enums import TaskStatus
from app.services.task_store import RedisTaskStore


@pytest_asyncio.fixture
async def store() -> RedisTaskStore:
    return RedisTaskStore(
        fakeredis.aioredis.FakeRedis(decode_responses=True),
        ttl=60,
    )


@pytest.mark.asyncio
async def test_create_and_get(store):
    task = await store.create("create_vm", resource_id="vm-001")
    fetched = await store.get(str(task.task_id))
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.status == TaskStatus.PENDING
    assert fetched.resource_id == "vm-001"


@pytest.mark.asyncio
async def test_get_missing_returns_none(store):
    result = await store.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_update_missing_task_is_a_noop(store):
    # Should return without raising even if the task doesn't exist.
    await store.update("nonexistent-id", status=TaskStatus.FAILED)


@pytest.mark.asyncio
async def test_update_sets_all_optional_fields(store):
    task = await store.create("resize_vm")
    task_id = str(task.task_id)
    await store.update(
        task_id,
        status=TaskStatus.SUCCESS,
        resource_id="vm-updated",
        error="none",
        result={"key": "value"},
    )
    fetched = await store.get(task_id)
    assert fetched.status == TaskStatus.SUCCESS
    assert fetched.resource_id == "vm-updated"
    assert fetched.error == "none"
    assert fetched.result == {"key": "value"}


@pytest.mark.asyncio
async def test_list_all_empty_store(store):
    tasks = await store.list_all()
    assert tasks == []


@pytest.mark.asyncio
async def test_list_all_returns_all_tasks(store):
    await store.create("op_one")
    await store.create("op_two")
    tasks = await store.list_all()
    assert len(tasks) == 2
