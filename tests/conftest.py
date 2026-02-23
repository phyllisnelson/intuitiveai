"""Shared pytest fixtures.

Tests never touch a real OpenStack cluster.  The MockOpenStackService is
injected via FastAPI's dependency_overrides mechanism so the full ASGI
stack is exercised without any network calls.

A FakeRedis-backed RedisTaskStore is shared between the mock service and
the FastAPI DI override so that tasks created by the mock are visible to
the tasks endpoint, and state never leaks between tests.

Auth: all default fixtures configure API_KEY="test-key" and send the key
on every request, exercising the real authentication code path.
"""

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.enums import VMState
from app.services.task_store import RedisTaskStore
from tests.mocks.factories import (
    FlavorResponseFactory,
    ImageResponseFactory,
    VMResponseFactory,
)
from tests.mocks.openstack import MockOpenStackService

TEST_API_KEY = "test-key"


@pytest.fixture
def task_store() -> RedisTaskStore:
    """Fresh FakeRedis-backed task store per test — fully isolated state."""
    return RedisTaskStore(
        fakeredis.aioredis.FakeRedis(decode_responses=True),
        ttl=60,
    )


@pytest.fixture
def mock_service(task_store: RedisTaskStore) -> MockOpenStackService:
    """Fresh MockOpenStackService per test, seeded with factory_boy data."""
    flavors = FlavorResponseFactory.build_batch(4)
    images = ImageResponseFactory.build_batch(3)
    vms = [
        VMResponseFactory(status=VMState.ACTIVE),
        VMResponseFactory(status=VMState.ACTIVE),
        VMResponseFactory(status=VMState.SHUTOFF),
    ]
    return MockOpenStackService(
        task_store=task_store,
        vms=vms,
        flavors=flavors,
        images=images,
    )


@pytest.fixture
def app(mock_service: MockOpenStackService, task_store: RedisTaskStore):
    """FastAPI app with real dependencies replaced by test doubles.

    Configures API_KEY=test-key so the real auth code path is exercised.
    """
    application = create_app()
    application.dependency_overrides[deps.get_openstack_service] = lambda: mock_service
    application.dependency_overrides[deps.get_task_store] = lambda: task_store
    application.dependency_overrides[get_settings] = lambda: Settings(
        api_key=TEST_API_KEY,
    )
    return application


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as c:
        yield c


@pytest_asyncio.fixture
async def async_client(app) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": TEST_API_KEY},
    ) as ac:
        yield ac
