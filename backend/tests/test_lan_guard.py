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


class TestLanGuardHostnameAliases:
    @pytest.fixture(autouse=True)
    def reset_allowed_hosts(self):
        import backend.app.middleware.lan_guard as lg

        lg._allowed_hosts = None
        yield
        lg._allowed_hosts = None

    @pytest.fixture
    def fixed_hostname_detection(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg.socket, "gethostname", lambda: "shop-floor-01")
        monkeypatch.setattr(lg.socket, "getfqdn", lambda: "shop-floor-01.example.lan")
        monkeypatch.setattr(lg.socket, "getaddrinfo", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(lg, "_probe_outbound_ipv4", lambda: None)
        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "127.0.0.1")
        return lg

    def test_detected_hosts_include_mdns_alias(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg.socket, "gethostname", lambda: "shop-floor-01")
        monkeypatch.setattr(lg.socket, "getfqdn", lambda: "shop-floor-01.example.lan")
        monkeypatch.setattr(lg.socket, "getaddrinfo", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(lg, "_probe_outbound_ipv4", lambda: None)

        allowed = lg._detect_allowed_hosts()

        assert "shop-floor-01" in allowed
        assert "shop-floor-01.local" in allowed
        assert "shop-floor-01.example.lan" in allowed

    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",
            "localhost",
            "shop-floor-01",
            "shop-floor-01.local",
            "shop-floor-01.example.lan",
            "SHOP-FLOOR-01.LOCAL.",
        ],
    )
    def test_expected_hostname_aliases_pass_end_to_end(self, fixed_hostname_detection, host):
        with TestClient(app) as c:
            resp = c.get("/health", headers=_set_host(None, host))
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_random_host_still_blocked(self, fixed_hostname_detection):
        with TestClient(app) as c:
            resp = c.get("/health", headers=_set_host(None, "evil.example"))
            assert resp.status_code == 421
            assert resp.json()["detail"] == "host not allowed"


class TestLanGuardDisabled:
    def test_guard_disabled_bad_host_passes(self, client, monkeypatch):
        from backend.app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "lan_guard_enabled", False)
        resp = client.get("/health", headers=_set_host(None, "evil.com"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestLanGuardAllowedHostsEnv:
    """TAGLEDGER_ALLOWED_HOSTS lets the Tauri launcher inject the LAN IP it
    chose for the QR (the UDP probe may pick the wrong interface on multi-homed
    hosts). Regression-guard the env path so it doesn't silently drop."""

    def test_env_hosts_added_to_detection(self, monkeypatch):
        monkeypatch.setenv("TAGLEDGER_ALLOWED_HOSTS", "tauri.local, 10.99.0.1 ")
        import backend.app.middleware.lan_guard as lg

        allowed = lg._detect_allowed_hosts()
        assert "tauri.local" in allowed
        assert "10.99.0.1" in allowed

    def test_env_host_accepted_end_to_end(self, monkeypatch):
        monkeypatch.setenv("TAGLEDGER_ALLOWED_HOSTS", "myalias.lan")
        import backend.app.middleware.lan_guard as lg

        # Force re-detection so the env value is picked up.
        lg._allowed_hosts = None
        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "127.0.0.1")
        with TestClient(app) as c:
            resp = c.get("/health", headers=_set_host(None, "myalias.lan"))
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        # Reset cache so other tests get a fresh detection.
        lg._allowed_hosts = None
