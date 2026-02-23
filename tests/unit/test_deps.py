"""Unit tests for FastAPI dependency providers (app.api.deps)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import deps
from app.core.config import Settings
from app.services.task_store import RedisTaskStore


@pytest.fixture(autouse=True)
def reset_singletons():
    """Wipe module-level singletons before and after every test."""
    deps._task_store_instance = None
    deps._service_instance = None
    deps._arq_pool_instance = None
    yield
    deps._task_store_instance = None
    deps._service_instance = None
    deps._arq_pool_instance = None


class TestGetTaskStore:
    def test_no_redis_url_raises(self):
        with pytest.raises(ValueError, match="REDIS_URL"):
            deps.get_task_store(Settings(redis_url=None))

    def test_creates_store_with_correct_args(self):
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_from_url.return_value = MagicMock()
            store = deps.get_task_store(Settings(redis_url="redis://myhost:6379"))
        assert isinstance(store, RedisTaskStore)
        mock_from_url.assert_called_once_with(
            "redis://myhost:6379",
            decode_responses=True,
        )

    def test_returns_singleton_on_repeated_calls(self):
        settings = Settings(redis_url="redis://localhost:6379")
        with patch("redis.asyncio.from_url", return_value=MagicMock()):
            s1 = deps.get_task_store(settings)
            s2 = deps.get_task_store(settings)
        assert s1 is s2


class TestGetArqPool:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_redis_url(self):
        pool = await deps.get_arq_pool(Settings(redis_url=None))
        assert pool is None

    @pytest.mark.asyncio
    async def test_creates_pool_when_redis_url_set(self):
        mock_pool = AsyncMock()
        with patch("app.api.deps.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool
            pool = await deps.get_arq_pool(Settings(redis_url="redis://localhost:6379"))
        assert pool is mock_pool

    @pytest.mark.asyncio
    async def test_returns_singleton_on_repeated_calls(self):
        with patch("app.api.deps.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = AsyncMock()
            p1 = await deps.get_arq_pool(Settings(redis_url="redis://localhost:6379"))
            p2 = await deps.get_arq_pool(Settings(redis_url="redis://localhost:6379"))
        assert p1 is p2
        mock_create.assert_called_once()


class TestGetOpenStackService:
    @pytest.mark.asyncio
    async def test_creates_service_with_correct_args(self):
        task_store = MagicMock()
        settings = Settings()
        with patch("app.api.deps.OpenStackService") as MockService:
            MockService.return_value = MagicMock()
            service = await deps.get_openstack_service(
                settings,
                task_store,
                arq_pool=None,
            )
        MockService.assert_called_once_with(settings, task_store, arq_pool=None)
        assert service is MockService.return_value

    @pytest.mark.asyncio
    async def test_returns_singleton_on_repeated_calls(self):
        task_store = MagicMock()
        settings = Settings()
        with patch("app.api.deps.OpenStackService") as MockService:
            MockService.return_value = MagicMock()
            svc1 = await deps.get_openstack_service(settings, task_store, arq_pool=None)
            svc2 = await deps.get_openstack_service(settings, task_store, arq_pool=None)
        assert svc1 is svc2
        MockService.assert_called_once()
