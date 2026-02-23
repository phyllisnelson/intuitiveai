"""Domain exceptions for the VM lifecycle service.

These are raised by the service layer and caught by the FastAPI exception
handlers registered in ``app/main.py``.
"""

from http import HTTPStatus


class VMAPIError(Exception):
    """Base class for all VM API errors."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class VMNotFoundError(VMAPIError):
    status_code = HTTPStatus.NOT_FOUND
    detail = "Virtual machine not found."


class FlavorNotFoundError(VMAPIError):
    status_code = HTTPStatus.NOT_FOUND
    detail = "Flavor not found."


class ImageNotFoundError(VMAPIError):
    status_code = HTTPStatus.NOT_FOUND
    detail = "Image not found."


class TaskNotFoundError(VMAPIError):
    status_code = HTTPStatus.NOT_FOUND
    detail = "Task not found."


class InvalidVMStateError(VMAPIError):
    """Raised when the requested action is incompatible with the VM's current
    power state (e.g. trying to start an already-running VM)."""

    status_code = HTTPStatus.CONFLICT
    detail = "Operation not permitted in the current VM state."


class VMOperationError(VMAPIError):
    """Raised when OpenStack rejects or fails an operation."""

    status_code = HTTPStatus.BAD_GATEWAY
    detail = "The OpenStack operation failed."


class OpenStackConnectionError(VMAPIError):
    """Raised when the service cannot reach the OpenStack endpoint."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    detail = "Cannot reach the OpenStack API. Check connectivity and credentials."


class AuthenticationError(VMAPIError):
    status_code = HTTPStatus.UNAUTHORIZED
    detail = "Missing or invalid API key."
