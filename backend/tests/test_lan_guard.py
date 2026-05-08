import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _set_host(headers: dict | None, host: str) -> dict:
    headers = dict(headers or {})
    headers["Host"] = host
    return headers


class TestLanGuardBadHost:
    def test_bad_host_header_returns_421(self, client, monkeypatch):
        resp = client.get("/health", headers=_set_host(None, "evil.com"))
        assert resp.status_code == 421
        assert resp.json()["detail"] == "host not allowed"


class TestLanGuardPublicSource:
    def test_public_source_ip_returns_403(self, client, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "8.8.8.8")
        resp = client.get("/health", headers=_set_host(None, "localhost"))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "public source not allowed"


class TestLanGuardLocalhost:
    def test_localhost_passes(self, client, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "127.0.0.1")
        resp = client.get("/health", headers=_set_host(None, "localhost"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestLanGuardDisabled:
    def test_guard_disabled_bad_host_passes(self, client, monkeypatch):
        from backend.app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "lan_guard_enabled", False)
        resp = client.get("/health", headers=_set_host(None, "evil.com"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
