"""Unit tests for the ImageClient sub-client (_image.py)."""

from unittest.mock import MagicMock, patch

import pytest

from tests.mocks.factories import ImageStubFactory


class TestListImages:
    @pytest.mark.asyncio
    async def test_returns_images(self, make_service):
        svc, _ = make_service()
        mock_conn = MagicMock()
        mock_conn.image.images.return_value = [ImageStubFactory()]
        with patch("openstack.connect", return_value=mock_conn):
            images, total = await svc.list_images()
        assert total == 1
        assert images[0].id == "img-001"

    @pytest.mark.asyncio
    async def test_malformed_image_skipped(self, make_service):
        svc, _ = make_service()
        bad_img = ImageStubFactory(
            id="bad",
            name=None,
            status=None,
            size=None,
            min_disk=None,
            min_ram=None,
            visibility=None,
            created_at=None,
        )
        bad_img.get.side_effect = RuntimeError("corrupt")
        good_img = ImageStubFactory(id="img-good")
        mock_conn = MagicMock()
        mock_conn.image.images.return_value = [bad_img, good_img]
        with patch("openstack.connect", return_value=mock_conn):
            images, total = await svc.list_images()
        assert total == 1
        assert images[0].id == "img-good"

    @pytest.mark.asyncio
    async def test_pagination(self, make_service):
        svc, _ = make_service()
        imgs = [ImageStubFactory(id=f"img-{i:02d}") for i in range(5)]
        mock_conn = MagicMock()
        mock_conn.image.images.return_value = imgs
        with patch("openstack.connect", return_value=mock_conn):
            images, total = await svc.list_images(limit=2, offset=1)
        assert total == 5
        assert images[0].id == "img-01"
