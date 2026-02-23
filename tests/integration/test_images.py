"""Tests for /api/v1/images."""

from http import HTTPStatus


class TestImages:
    base = "/api/v1/images"

    def test_list_images(self, client):
        resp = client.get(self.base)
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["total"] >= 3
        image = body["data"][0]
        assert "id" in image
        assert "name" in image
        assert "status" in image
