from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.auth import require_login, require_manager
from backend.app.config import get_settings
from backend.app.database import create_db_and_tables
from backend.app.models import User
from backend.app.routes import (
    auth,
    confirm,
    export,
    inventory,
    jobs,
    metrics,
    outbound,
    transfers,
    upload,
)
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


app = FastAPI(title="Machine Label OCR", version="0.1.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"
PAGES_DIR = Path(__file__).resolve().parent / "pages"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
def home_workbench(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    home_path = STATIC_DIR / "home.html"
    if not home_path.exists():
        raise HTTPException(status_code=404, detail="home page not found")
    return FileResponse(home_path)


@app.get("/capture", include_in_schema=False)
def demo_home(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    demo_path = STATIC_DIR / "demo.html"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="demo page not found")
    return FileResponse(demo_path)


@app.get("/mobile", include_in_schema=False)
def mobile_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    mobile_path = STATIC_DIR / "mobile.html"
    if not mobile_path.exists():
        raise HTTPException(status_code=404, detail="mobile page not found")
    return FileResponse(mobile_path)


@app.get("/history", include_in_schema=False)
def history_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    history_path = STATIC_DIR / "history.html"
    if not history_path.exists():
        raise HTTPException(status_code=404, detail="history page not found")
    return FileResponse(history_path)


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    dashboard_path = STATIC_DIR / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="dashboard page not found")
    return FileResponse(dashboard_path)


@app.get("/outbound", include_in_schema=False)
def outbound_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    outbound_path = STATIC_DIR / "outbound.html"
    if not outbound_path.exists():
        raise HTTPException(status_code=404, detail="outbound page not found")
    return FileResponse(outbound_path)


@app.get("/outbound-progress", include_in_schema=False)
def outbound_progress_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    outbound_progress_path = STATIC_DIR / "outbound_progress.html"
    if not outbound_progress_path.exists():
        raise HTTPException(status_code=404, detail="outbound progress page not found")
    return FileResponse(outbound_progress_path)


@app.get("/inventory", include_in_schema=False)
def inventory_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    inventory_path = STATIC_DIR / "inventory.html"
    if not inventory_path.exists():
        raise HTTPException(status_code=404, detail="inventory page not found")
    return FileResponse(inventory_path)


@app.get("/ops-health", include_in_schema=False)
def ops_health_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    ops_health_path = STATIC_DIR / "ops_health.html"
    if not ops_health_path.exists():
        raise HTTPException(status_code=404, detail="ops health page not found")
    return FileResponse(ops_health_path)


@app.get("/transfers", include_in_schema=False)
def transfers_page(_: Annotated[User, Depends(require_login)]) -> FileResponse:
    transfers_path = STATIC_DIR / "transfers.html"
    if not transfers_path.exists():
        raise HTTPException(status_code=404, detail="transfers page not found")
    return FileResponse(transfers_path)


@app.get("/admin", include_in_schema=False)
def admin_page(_: Annotated[User, Depends(require_manager)]) -> FileResponse:
    admin_path = PAGES_DIR / "admin.html"
    if not admin_path.exists():
        raise HTTPException(status_code=404, detail="admin page not found")
    return FileResponse(admin_path)


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    login_path = STATIC_DIR / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="login page not found")
    return FileResponse(login_path)


@app.get("/setup", include_in_schema=False)
def setup_page() -> FileResponse:
    setup_path = STATIC_DIR / "setup.html"
    if not setup_path.exists():
        raise HTTPException(status_code=404, detail="setup page not found")
    return FileResponse(setup_path)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url=f"/login?next={request.url.path}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(confirm.router)
app.include_router(export.router)
app.include_router(metrics.router)
app.include_router(outbound.router)
app.include_router(inventory.router)
app.include_router(transfers.router)
