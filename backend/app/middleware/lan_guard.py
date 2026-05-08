import ipaddress
import os
import socket

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.app.config import get_settings
from backend.app.pairing import is_paired

PAIRING_EXEMPT_PREFIXES = ("/pair", "/api/pairing", "/health", "/favicon.ico", "/static/")

LOOPBACK4 = ipaddress.IPv4Network("127.0.0.0/8")
LOOPBACK6 = ipaddress.IPv6Address("::1")

PRIVATE_RANGES = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
]


def _is_private_ipv4(ip: ipaddress.IPv4Address) -> bool:
    return any(ip in net for net in PRIVATE_RANGES)


def _get_remote_ip(request: Request) -> str:
    return request.client.host if request.client else "127.0.0.1"


def _probe_outbound_ipv4() -> str | None:
    """Find the LAN IPv4 of the interface used to reach the default gateway.

    `socket.gethostname()` is unreliable on macOS/Linux (often resolves only to
    127.0.1.1), which would cause the LanGuard to 421 legitimate phone traffic
    hitting `http://<lan-ip>:<port>`. This UDP-connect trick asks the kernel to
    pick the outbound interface without actually sending a packet.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _detect_allowed_hosts() -> set[str]:
    allowed: set[str] = {"localhost", "127.0.0.1", "[::1]"}
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if isinstance(ip, ipaddress.IPv4Address) and _is_private_ipv4(ip):
                allowed.add(str(ip))
            elif (
                isinstance(ip, ipaddress.IPv6Address)
                and not ip.is_loopback
                and not ip.is_link_local
            ):
                allowed.add(f"[{ip}]")
    except (OSError, RuntimeError):
        pass
    outbound = _probe_outbound_ipv4()
    if outbound:
        try:
            ip = ipaddress.IPv4Address(outbound)
            if _is_private_ipv4(ip):
                allowed.add(str(ip))
        except ValueError:
            pass
    # Tauri launcher (or tests) can inject extra hosts via env.
    extra = os.getenv("TAGLEDGER_ALLOWED_HOSTS", "")
    for raw in extra.split(","):
        host = raw.strip()
        if host:
            allowed.add(host)
    return allowed


_allowed_hosts: set[str] | None = None


def refresh_allowed_hosts() -> None:
    global _allowed_hosts
    _allowed_hosts = _detect_allowed_hosts()


def _lazy_allowed_hosts() -> set[str]:
    global _allowed_hosts
    if _allowed_hosts is None:
        _allowed_hosts = _detect_allowed_hosts()
    return _allowed_hosts


def _first_lan_ipv4() -> str | None:
    outbound = _probe_outbound_ipv4()
    if outbound:
        try:
            ip = ipaddress.IPv4Address(outbound)
            if _is_private_ipv4(ip):
                return str(ip)
        except ValueError:
            pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if isinstance(ip, ipaddress.IPv4Address) and _is_private_ipv4(ip):
                return str(ip)
    except (OSError, RuntimeError):
        pass
    return None


def _normalize_host(host_header: str) -> str:
    if ":" in host_header and not host_header.startswith("["):
        last_colon = host_header.rfind(":")
        maybe_port = host_header[last_colon + 1 :]
        if maybe_port.isdigit():
            return host_header[:last_colon]
    if host_header.startswith("[") and "]" in host_header:
        return host_header[: host_header.index("]") + 1]
    return host_header


def _is_loopback(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in LOOPBACK4:
        return True
    return False


def _is_private_or_loopback(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return _is_private_ipv4(ip) or ip in LOOPBACK4
    if isinstance(ip, ipaddress.IPv6Address):
        return ip == LOOPBACK6 or (not ip.is_link_local and ip.is_private)
    return False


class LanGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.lan_guard_enabled:
            return await call_next(request)

        host_header = request.headers.get("host", "")
        if host_header:
            host_only = _normalize_host(host_header)
            allowed = _lazy_allowed_hosts()
            if host_only not in allowed:
                return JSONResponse(
                    {"detail": "host not allowed"},
                    status_code=421,
                )

        remote_ip = _get_remote_ip(request)
        if not _is_private_or_loopback(remote_ip):
            return JSONResponse(
                {"detail": "public source not allowed"},
                status_code=403,
            )

        return await call_next(request)


class PairingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.pairing_enabled:
            return await call_next(request)

        remote_ip = _get_remote_ip(request)
        if _is_loopback(remote_ip):
            return await call_next(request)

        path = request.url.path
        for prefix in PAIRING_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        cookie_value = request.cookies.get("tl_pair")
        if not is_paired(cookie_value):
            return JSONResponse(
                {"detail": "pairing required"},
                status_code=403,
            )

        return await call_next(request)
