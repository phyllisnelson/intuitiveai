"""Image (Glance) sub-client — wraps openstacksdk image operations."""

from datetime import UTC, datetime

import structlog

from app.schemas.image import ImageResponse

log = structlog.get_logger(__name__)


class ImageClient:
    """Wraps Glance (image) API calls."""

    def __init__(self, run) -> None:
        self._run = run

    async def list_images(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImageResponse], int]:
        def _images(conn):
            return list(conn.image.images())

        raw = await self._run(_images)
        images = []
        for img in raw:
            try:
                images.append(
                    ImageResponse(
                        id=img.id,
                        name=img.name or "",
                        status=img.status or "unknown",
                        size_bytes=img.size,
                        min_disk_gb=img.min_disk or 0,
                        min_ram_mb=img.min_ram or 0,
                        visibility=img.visibility or "public",
                        os_distro=img.get("os_distro"),
                        os_version=img.get("os_version"),
                        created_at=(
                            datetime.fromisoformat(img.created_at)
                            if img.created_at
                            else datetime.now(UTC)
                        ),
                    ),
                )
            except Exception:
                continue
        return images[offset : offset + limit], len(images)
