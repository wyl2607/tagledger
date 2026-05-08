import secrets
import time

from backend.app.config import get_settings


class PairingRateLimited(Exception):
    pass


class PairingTokenInvalid(Exception):
    pass


PAIR_TOKEN_TTL_SECONDS = 600  # 10 minutes
RATE_WINDOW_SECONDS = 60  # failures counted within last 60s
BLOCK_SECONDS = 600  # blocked for 10 minutes after threshold

_pair_token: str | None = None
_pair_token_issued_at: float = 0.0
_paired_cookies: set[str] = set()
_failed_attempts: dict[str, list[float]] = {}
_blocked_until: dict[str, float] = {}


def _new_token() -> str:
    return secrets.token_urlsafe(24)[:32]


# Generate at import time so the very first GET /api/pairing/status has something.
_pair_token = _new_token()
_pair_token_issued_at = time.time()


def get_pair_token() -> str | None:
    """Return the current token if still within TTL, else None."""
    if _pair_token is None:
        return None
    if time.time() - _pair_token_issued_at > PAIR_TOKEN_TTL_SECONDS:
        return None
    return _pair_token


def regenerate_token() -> str:
    """Issue a new token AND invalidate every previously-paired cookie.

    Restart-equivalent semantics: anyone holding an old QR or an old
    tl_pair cookie is forced to pair again.
    """
    global _pair_token, _pair_token_issued_at
    _pair_token = _new_token()
    _pair_token_issued_at = time.time()
    _paired_cookies.clear()
    return _pair_token


def redeem(token: str, ip: str) -> str:
    global _pair_token
    settings = get_settings()
    now = time.time()
    limit = settings.pairing_rate_limit_per_min

    blocked_at = _blocked_until.get(ip, 0.0)
    if blocked_at > now:
        raise PairingRateLimited("rate limited")
    if blocked_at and blocked_at <= now:
        # block window passed; clear bookkeeping
        _blocked_until.pop(ip, None)
        _failed_attempts.pop(ip, None)

    window_start = now - RATE_WINDOW_SECONDS
    recent = [ts for ts in _failed_attempts.get(ip, []) if ts > window_start]
    _failed_attempts[ip] = recent

    current = get_pair_token()  # honors TTL
    if current is None or token != current:
        recent.append(now)
        if len(recent) >= limit:
            _blocked_until[ip] = now + BLOCK_SECONDS
        raise PairingTokenInvalid("invalid token")

    _pair_token = None  # single-use
    cookie_value = secrets.token_urlsafe(32)
    _paired_cookies.add(cookie_value)
    return cookie_value


def is_paired(cookie_value: str | None) -> bool:
    return cookie_value is not None and cookie_value in _paired_cookies
