import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from backend.app.config import get_settings
from backend.app.database import create_db_and_tables, get_session
from backend.app.middleware.lan_guard import LanGuardMiddleware, PairingMiddleware
from backend.app.routes import (
    auth,
    confirm,
    export,
    inventory,
    jobs,
    metrics,
    outbound,
    pairing,
    signoff,
    transfers,
    upload,
)
from backend.app.services.auth_service import CSRF_COOKIE, CSRF_HEADER, users_exist
from backend.app.workers.submit_worker import enqueue_pending_confirmed


def restore_pending_submissions() -> int:
    if not get_settings().enable_saas_submit:
        return 0
    return enqueue_pending_confirmed()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    restore_pending_submissions()
    yield


app = FastAPI(title="TagLedger", version="0.1.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/setup",
    "/api/pairing/redeem",
    "/api/pairing/regenerate",
}
CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    settings = get_settings()
    if (
        settings.csrf_protection
        and request.method.upper() in CSRF_METHODS
        and request.url.path not in CSRF_EXEMPT_PATHS
    ):
        header_token = request.headers.get(CSRF_HEADER)
        cookie_token = request.cookies.get(CSRF_COOKIE)
        if (
            not header_token
            or not cookie_token
            or not hmac.compare_digest(
                header_token,
                cookie_token,
            )
        ):
            return Response(
                content='{"detail":"CSRF validation failed"}',
                status_code=403,
                media_type="application/json",
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/runtime/status")
def runtime_status(request: Request) -> dict[str, bool | str]:
    settings = get_settings()
    base_url = str(request.base_url).rstrip("/")
    return {
        "ocr_provider": settings.ocr_provider,
        "enable_barcode": settings.enable_barcode,
        "enable_saas_submit": settings.enable_saas_submit,
        "dry_run": settings.dry_run,
        "mobile_url": f"{base_url}/mobile",
        "history_url": f"{base_url}/history",
    }


@app.get("/", include_in_schema=False)
def portal_page(session: Session = Depends(get_session)) -> Response:
    if not users_exist(session):
        return RedirectResponse(url="/setup", status_code=303)
    portal_path = STATIC_DIR / "portal.html"
    if not portal_path.exists():
        raise HTTPException(status_code=404, detail="portal page not found")
    return FileResponse(portal_path)


def demo_home() -> FileResponse:
    demo_path = STATIC_DIR / "demo.html"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="demo page not found")
    return FileResponse(demo_path)


@app.get("/capture", include_in_schema=False)
def capture_page() -> FileResponse:
    return demo_home()


@app.get("/workbench", include_in_schema=False)
def workbench_page() -> FileResponse:
    home_path = STATIC_DIR / "home.html"
    if not home_path.exists():
        raise HTTPException(status_code=404, detail="home page not found")
    return FileResponse(home_path)


@app.get("/mobile", include_in_schema=False)
def mobile_page() -> FileResponse:
    mobile_path = STATIC_DIR / "mobile.html"
    if not mobile_path.exists():
        raise HTTPException(status_code=404, detail="mobile page not found")
    return FileResponse(mobile_path)


@app.get("/history", include_in_schema=False)
def history_page() -> FileResponse:
    history_path = STATIC_DIR / "history.html"
    if not history_path.exists():
        raise HTTPException(status_code=404, detail="history page not found")
    return FileResponse(history_path)


@app.get("/dashboard", include_in_schema=False)
def dashboard_page() -> FileResponse:
    dashboard_path = STATIC_DIR / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="dashboard page not found")
    return FileResponse(dashboard_path)


@app.get("/outbound", include_in_schema=False)
def outbound_page() -> FileResponse:
    outbound_path = STATIC_DIR / "outbound.html"
    if not outbound_path.exists():
        raise HTTPException(status_code=404, detail="outbound page not found")
    return FileResponse(outbound_path)


@app.get("/transfers", include_in_schema=False)
def transfers_page() -> FileResponse:
    transfers_path = STATIC_DIR / "transfers.html"
    if not transfers_path.exists():
        raise HTTPException(status_code=404, detail="transfers page not found")
    return FileResponse(transfers_path)


@app.get("/inventory", include_in_schema=False)
def inventory_page() -> FileResponse:
    inventory_path = STATIC_DIR / "inventory.html"
    if not inventory_path.exists():
        raise HTTPException(status_code=404, detail="inventory page not found")
    return FileResponse(inventory_path)


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    login_path = STATIC_DIR / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="login page not found")
    return FileResponse(login_path)


@app.get("/setup", include_in_schema=False)
def setup_page(session: Session = Depends(get_session)) -> Response:
    setup_path = STATIC_DIR / "setup.html"
    if not setup_path.exists():
        raise HTTPException(status_code=404, detail="setup page not found")
    if users_exist(session):
        return RedirectResponse(url="/login", status_code=303)
    return FileResponse(setup_path)


@app.get("/signoff", include_in_schema=False)
def signoff_page() -> FileResponse:
    signoff_path = STATIC_DIR / "signoff.html"
    if not signoff_path.exists():
        raise HTTPException(status_code=404, detail="signoff page not found")
    return FileResponse(signoff_path)


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    admin_path = STATIC_DIR / "admin.html"
    if not admin_path.exists():
        raise HTTPException(status_code=404, detail="admin page not found")
    return FileResponse(admin_path)


app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(confirm.router)
app.include_router(export.router)
app.include_router(inventory.router)
app.include_router(metrics.router)
app.include_router(outbound.router)
app.include_router(transfers.router)
app.include_router(signoff.router)
app.include_router(auth.router)
app.include_router(auth.admin_router)
app.include_router(auth.workbench_router)
app.include_router(pairing.router)


@app.get("/pair", include_in_schema=False)
def pair_page() -> FileResponse:
    pair_path = STATIC_DIR / "pair.html"
    if not pair_path.exists():
        raise HTTPException(status_code=404, detail="pair page not found")
    return FileResponse(pair_path)


app.add_middleware(LanGuardMiddleware)
app.add_middleware(PairingMiddleware)
