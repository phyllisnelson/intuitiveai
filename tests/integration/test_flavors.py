"""Tests for /api/v1/flavors."""

from http import HTTPStatus


class TestFlavors:
    base = "/api/v1/flavors"

    def test_list_flavors(self, client):
        resp = client.get(self.base)
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["total"] >= 4
        flavor = body["data"][0]
        assert "id" in flavor
        assert "vcpus" in flavor
        assert "ram_mb" in flavor
        assert "disk_gb" in flavor
