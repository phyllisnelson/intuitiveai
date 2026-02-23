"""VM action schemas — request and response models for sub-resource operations."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.enums import VMAction


class VMActionRequest(BaseModel):
    action: VMAction
    reboot_type: str | None = Field(
        default=None,
        description="Only used with 'reboot'. Values: 'SOFT' (default) or 'HARD'.",
    )


class VMResizeRequest(BaseModel):
    flavor_id: str = Field(..., examples=["m1.large"])


class SnapshotCreateRequest(BaseModel):
    """Request body for POST /api/v1/vms/{id}/snapshots."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["vm-scada-prod-03-snap-20250101"],
    )
    metadata: dict[str, str] = Field(default_factory=dict)


class ConsoleResponse(BaseModel):
    type: str
    url: str


class SnapshotResponse(BaseModel):
    id: str
    name: str
    status: str
    source_vm_id: str
    created_at: datetime
