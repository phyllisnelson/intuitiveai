"""VM schemas — request and response models for VM CRUD operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import VMState


class VMCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["vm-scada-prod-03"])
    flavor_id: str = Field(..., examples=["m1.medium"])
    image_id: str = Field(..., examples=["ubuntu-22.04-lts"])
    network_id: str | None = Field(
        default=None,
        description="Network UUID. Falls back to OPENSTACK_DEFAULT_NETWORK_ID env var.",
    )
    key_name: str | None = Field(default=None, examples=["ops-key"])
    security_groups: list[str] = Field(
        default_factory=lambda: ["default"],
        examples=[["default", "ot-sg"]],
    )
    user_data: str | None = Field(
        default=None,
        description="Cloud-init user data (plain text, not base64).",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        examples=[{"env": "prod", "owner": "ot-team"}],
    )

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("VM name must not contain spaces.")
        return v


class AddressInfo(BaseModel):
    version: int
    addr: str
    type: str | None = None


class VMResponse(BaseModel):
    id: str
    name: str
    status: VMState
    flavor_id: str
    flavor_name: str | None = None
    image_id: str | None = None
    image_name: str | None = None
    addresses: dict[str, list[AddressInfo]] = Field(default_factory=dict)
    key_name: str | None = None
    security_groups: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None
    host_id: str | None = None
    availability_zone: str | None = None

    model_config = {"from_attributes": True}
