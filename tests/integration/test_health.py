"""Tests for /health and /ready endpoints."""

from http import HTTPStatus


class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "region" in body

    def test_ready_returns_200(self, client):
        resp = client.get("/ready")
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["ready"] is True
        assert "region" in body

    def test_root_returns_service_info(self, client):
        resp = client.get("/")
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert "service" in body
        assert "docs" in body
