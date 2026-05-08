import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.pairing import (
    get_pair_token as pair_get_token,
)
from backend.app.pairing import (
    redeem as pair_redeem,
)
from backend.app.pairing import (
    regenerate_token as pair_regenerate,
)


@pytest.fixture(autouse=True)
def _reset_pairing_state():
    import backend.app.pairing as pm

    pm._pair_token = pm._new_token()
    pm._pair_token_issued_at = pm.time.time()
    pm._paired_cookies.clear()
    pm._failed_attempts.clear()
    pm._blocked_until.clear()
    yield
    pm._pair_token = None
    pm._paired_cookies.clear()
    pm._failed_attempts.clear()
    pm._blocked_until.clear()


def _patch_remote(monkeypatch, ip: str):
    import backend.app.middleware.lan_guard as lg

    monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: ip)


def _headers(extra: dict | None = None) -> dict:
    h = {"Host": "localhost"}
    if extra:
        h.update(extra)
    return h


class TestPairingStatus:
    def test_status_from_loopback_returns_token(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "127.0.0.1")
        with TestClient(app) as c:
            resp = c.get("/api/pairing/status", headers=_headers())
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_token"] is True
            assert data["token"] is not None
            assert "lan_url" in data

    def test_status_from_non_loopback_returns_403(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        with TestClient(app) as c:
            resp = c.get("/api/pairing/status", headers=_headers())
            assert resp.status_code == 403


class TestPairingRedeem:
    def test_redeem_valid_token_sets_cookie(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        token = pair_get_token()
        with TestClient(app) as c:
            resp = c.post(
                "/api/pairing/redeem",
                json={"token": token},
                headers=_headers(),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "tl_pair" in resp.cookies

    def test_redeem_same_token_twice_second_401(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        token = pair_get_token()
        with TestClient(app) as c:
            resp1 = c.post(
                "/api/pairing/redeem",
                json={"token": token},
                headers=_headers(),
            )
            assert resp1.status_code == 200

            resp2 = c.post(
                "/api/pairing/redeem",
                json={"token": token},
                headers=_headers(),
            )
            assert resp2.status_code == 401

    def test_redeem_bad_token_returns_401(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        with TestClient(app) as c:
            resp = c.post(
                "/api/pairing/redeem",
                json={"token": "bad-token"},
                headers=_headers(),
            )
            assert resp.status_code == 401

    def test_six_bad_redeems_rate_limited(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        with TestClient(app) as c:
            for i in range(5):
                resp = c.post(
                    "/api/pairing/redeem",
                    json={"token": "bad-token"},
                    headers=_headers(),
                )
                assert resp.status_code == 401, f"attempt {i + 1} expected 401"

            resp = c.post(
                "/api/pairing/redeem",
                json={"token": "bad-token"},
                headers=_headers(),
            )
            assert resp.status_code == 429


class TestPairingEnforcement:
    def test_non_loopback_no_cookie_returns_403(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        with TestClient(app) as c:
            resp = c.get("/api/jobs", headers=_headers())
            assert resp.status_code == 403
            assert resp.json()["detail"] == "pairing required"

    def test_non_loopback_with_valid_cookie_passes_pairing(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        token = pair_get_token()
        cookie_value = pair_redeem(token, "192.168.1.50")
        with TestClient(app) as c:
            c.cookies.set("tl_pair", cookie_value)
            resp = c.get("/api/jobs", headers=_headers())
            assert resp.status_code != 403 or resp.json().get("detail") != "pairing required"

    def test_loopback_no_cookie_passes_pairing(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "127.0.0.1")
        with TestClient(app) as c:
            resp = c.get("/api/jobs", headers=_headers())
            assert resp.status_code != 403 or resp.json().get("detail") != "pairing required"


class TestPairingRegenerate:
    def test_old_token_invalid_after_regenerate(self, monkeypatch):
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        old_token = pair_get_token()
        pair_regenerate()
        with TestClient(app) as c:
            resp = c.post(
                "/api/pairing/redeem",
                json={"token": old_token},
                headers=_headers(),
            )
            assert resp.status_code == 401

    def test_old_cookie_invalidated_after_regenerate(self, monkeypatch):
        """Per Codex spec: regenerate forces every paired device to pair again."""
        import backend.app.middleware.lan_guard as lg

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        token_before = pair_get_token()
        cookie_value = pair_redeem(token_before, "192.168.1.50")
        pair_regenerate()
        assert pair_get_token() != token_before

        import backend.app.pairing as pm

        assert pm.is_paired(cookie_value) is False

        # Sanity: a request bearing the now-stale cookie is rejected by the middleware.
        with TestClient(app) as c:
            c.cookies.set("tl_pair", cookie_value)
            resp = c.get("/api/jobs", headers=_headers())
            assert resp.status_code == 403
            assert resp.json()["detail"] == "pairing required"


class TestPairingTTL:
    def test_expired_token_returns_401(self, monkeypatch):
        """Token older than PAIR_TOKEN_TTL_SECONDS is treated as missing."""
        import backend.app.middleware.lan_guard as lg
        import backend.app.pairing as pm

        monkeypatch.setattr(lg, "_get_remote_ip", lambda _r: "192.168.1.50")
        token = pm._pair_token
        # Backdate issuance past the TTL.
        pm._pair_token_issued_at = pm.time.time() - pm.PAIR_TOKEN_TTL_SECONDS - 1
        assert pm.get_pair_token() is None

        with TestClient(app) as c:
            resp = c.post(
                "/api/pairing/redeem",
                json={"token": token},
                headers=_headers(),
            )
            assert resp.status_code == 401
