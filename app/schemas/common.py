"""Shared response envelopes."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class APIResponse(BaseModel, Generic[T]):
    """Standard envelope wrapping every successful response body."""

    data: T
    meta: dict = Field(default_factory=dict)


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int = 1
    page_size: int

    @classmethod
    def from_page(
        cls,
        data: list[T],
        total: int,
        limit: int,
        offset: int,
    ) -> "PaginatedResponse[T]":
        return cls(
            data=data,
            total=total,
            page=offset // limit + 1,
            page_size=limit,
        )
