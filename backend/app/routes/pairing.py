from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.middleware import lan_guard
from backend.app.pairing import (
    PairingRateLimited,
    PairingTokenInvalid,
    get_pair_token,
    redeem,
    regenerate_token,
)

router = APIRouter(prefix="/api/pairing", tags=["pairing"])


def _loopback_only(request: Request) -> JSONResponse | None:
    if not lan_guard._is_loopback(lan_guard._get_remote_ip(request)):
        return JSONResponse({"detail": "loopback only"}, status_code=403)
    return None


def _get_lan_url(request: Request) -> str:
    port = request.url.port or "8000"
    lan_ip = lan_guard._first_lan_ipv4()
    token = get_pair_token()
    if token and lan_ip:
        return f"http://{lan_ip}:{port}/pair?t={token}"
    host = request.headers.get("host", f"localhost:{port}")
    if ":" in host and not host.startswith("["):
        host_only = host.rsplit(":", 1)[0]
    else:
        host_only = host
    return f"http://{host_only}:{port}/pair"


@router.get("/status")
def pairing_status(request: Request):
    result = _loopback_only(request)
    if result is not None:
        return result
    token = get_pair_token()
    return JSONResponse(
        {
            "has_token": token is not None,
            "token": token,
            "lan_url": _get_lan_url(request),
        }
    )


@router.post("/regenerate")
def pairing_regenerate(request: Request):
    result = _loopback_only(request)
    if result is not None:
        return result
    token = regenerate_token()
    return JSONResponse(
        {
            "has_token": True,
            "token": token,
            "lan_url": _get_lan_url(request),
        }
    )


class RedeemRequest(BaseModel):
    token: str


@router.post("/redeem")
async def pairing_redeem(request: Request, body: RedeemRequest):
    ip = lan_guard._get_remote_ip(request)
    try:
        cookie_value = redeem(body.token, ip)
    except PairingRateLimited:
        return JSONResponse({"detail": "rate limited"}, status_code=429)
    except PairingTokenInvalid:
        return JSONResponse({"detail": "invalid token"}, status_code=401)

    response = JSONResponse({"ok": True})
    response.set_cookie("tl_pair", cookie_value, httponly=True, samesite="lax", path="/")
    return response
