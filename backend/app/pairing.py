import secrets
import time

from backend.app.config import get_settings


class PairingRateLimited(Exception):
    pass


class PairingTokenInvalid(Exception):
    pass


_pair_token: str | None = secrets.token_urlsafe(24)[:32]
_paired_cookies: set[str] = set()
_failed_attempts: dict[str, list[float]] = {}


def get_pair_token() -> str | None:
    return _pair_token


def regenerate_token() -> str:
    global _pair_token
    _pair_token = secrets.token_urlsafe(24)[:32]
    return _pair_token


def redeem(token: str, ip: str) -> str:
    global _pair_token
    settings = get_settings()
    now = time.time()
    limit = settings.pairing_rate_limit_per_min
    block_minutes = settings.pairing_block_minutes

    window = now - block_minutes * 60
    entries = _failed_attempts.get(ip, [])
    recent = [ts for ts in entries if ts > window]
    _failed_attempts[ip] = recent

    if len(recent) >= limit:
        raise PairingRateLimited("rate limited")

    if _pair_token is None or token != _pair_token:
        _failed_attempts[ip].append(now)
        raise PairingTokenInvalid("invalid token")

    _pair_token = None
    cookie_value = secrets.token_urlsafe(32)
    _paired_cookies.add(cookie_value)
    return cookie_value


def is_paired(cookie_value: str | None) -> bool:
    return cookie_value is not None and cookie_value in _paired_cookies
