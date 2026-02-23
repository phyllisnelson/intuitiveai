"""Task schema — async operation tracking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.enums import TaskStatus


class TaskResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    operation: str
    resource_id: str | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    result: dict | None = None
