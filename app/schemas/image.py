"""Pydantic response model for OpenStack Glance images."""

from datetime import datetime

from pydantic import BaseModel


class ImageResponse(BaseModel):
    id: str
    name: str
    status: str
    size_bytes: int | None = None
    min_disk_gb: int = 0
    min_ram_mb: int = 0
    visibility: str = "public"
    os_distro: str | None = None
    os_version: str | None = None
    created_at: datetime
