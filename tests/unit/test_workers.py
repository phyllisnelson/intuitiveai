"""Unit tests for app.workers.tasks and app.workers.main."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.openstack_service import OpenStackService
from app.workers.main import shutdown, startup
from app.workers.tasks import (
    do_delete,
    do_resize,
    poll_until_active,
)


class TestWorkerTasks:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("worker_func", "service_method", "call_args", "call_kwargs", "expected_args"),
        [
            (
                poll_until_active,
                "poll_until_active",
                ("vm-1", "t-1"),
                {"timeout": 30},
                ("vm-1", "t-1", 30),
            ),
            (do_delete, "do_delete", ("vm-1", "t-1"), {}, ("vm-1", "t-1")),
            (
                do_resize,
                "do_resize",
                ("vm-1", "t-1", "medium"),
                {},
                ("vm-1", "t-1", "medium"),
            ),
        ],
    )
    async def test_delegates_to_service(
        self,
        worker_func,
        service_method: str,
        call_args: tuple,
        call_kwargs: dict,
        expected_args: tuple,
    ):
        svc = AsyncMock()
        await worker_func({"svc": svc}, *call_args, **call_kwargs)
        getattr(svc, service_method).assert_awaited_once_with(*expected_args)


class TestWorkerStartup:
    @pytest.mark.asyncio
    async def test_startup_creates_service_in_ctx(self):
        ctx: dict = {}
        with patch("redis.asyncio.from_url", return_value=MagicMock()):
            with patch("app.workers.main.get_settings") as mock_settings:
                mock_settings.return_value = Settings(
                    redis_url="redis://localhost:6379",
                )
                await startup(ctx)
        assert "svc" in ctx
        assert isinstance(ctx["svc"], OpenStackService)

    @pytest.mark.asyncio
    async def test_shutdown_is_noop(self):
        await shutdown({})
