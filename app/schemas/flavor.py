"""Pydantic response model for OpenStack compute flavors."""

from pydantic import BaseModel


class FlavorResponse(BaseModel):
    id: str
    name: str
    vcpus: int
    ram_mb: int
    disk_gb: int
    is_public: bool = True
    description: str | None = None
