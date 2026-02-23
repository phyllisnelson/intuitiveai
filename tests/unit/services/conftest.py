"""Shared fixtures for unit/services tests."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.openstack_service import OpenStackService
from tests.mocks.factories import TaskResponseFactory


def make_settings(**kwargs):
    return Settings(
        openstack_auth_url="http://keystone:5000/v3",
        openstack_username="test",
        openstack_password="secret",
        **kwargs,
    )


@pytest.fixture
def task_store():
    store = AsyncMock()
    store.create.return_value = TaskResponseFactory()
    return store


@pytest.fixture
def make_service(task_store):
    """Fixture factory: call ``make_service()`` inside a test to get ``(svc, store)``.

    Accepts optional kwargs:
        make_service()                       → plain service, no arq pool
        make_service(arq_pool=AsyncMock())   → service with arq pool
        make_service(ts=custom_store)        → service with a different task store
    """

    def _factory(ts=None, arq_pool=None, **settings_kwargs):
        store = ts if ts is not None else task_store
        svc = OpenStackService(
            make_settings(**settings_kwargs),
            store,
            arq_pool=arq_pool,
        )
        return svc, store

    return _factory
