"""Unit tests for app.core.handlers."""

from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.exceptions import (
    FlavorNotFoundError,
    InvalidVMStateError,
    OpenStackConnectionError,
    VMNotFoundError,
    VMOperationError,
)
from app.core.handlers import (
    _generic_error_handler,
    _vm_api_error_handler,
    handle_domain_error,
)


@pytest.mark.parametrize(
    "exc,expected_status",
    [
        (VMNotFoundError("vm"), HTTPStatus.NOT_FOUND),
        (FlavorNotFoundError("f"), HTTPStatus.NOT_FOUND),
        (InvalidVMStateError("s"), HTTPStatus.CONFLICT),
        (VMOperationError("e"), HTTPStatus.BAD_GATEWAY),
        (OpenStackConnectionError("e"), HTTPStatus.SERVICE_UNAVAILABLE),
    ],
)
def test_handle_domain_error_raises_http_exception_for_known_type(exc, expected_status):
    with pytest.raises(HTTPException) as exc_info:
        handle_domain_error(exc)
    assert exc_info.value.status_code == expected_status


def test_handle_domain_error_reraises_unknown_exception():
    exc = RuntimeError("something unexpected")
    with pytest.raises(RuntimeError):
        handle_domain_error(exc)


@pytest.mark.asyncio
async def test_vm_api_error_handler_returns_correct_status():
    request = MagicMock()
    exc = VMNotFoundError("vm not found")
    response = await _vm_api_error_handler(request, exc)
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_generic_error_handler_returns_500():
    request = MagicMock()
    exc = RuntimeError("boom")
    response = await _generic_error_handler(request, exc)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
