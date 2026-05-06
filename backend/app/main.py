from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.database import create_db_and_tables
from backend.app.routes import confirm, export, jobs, metrics, outbound, transfers, upload
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
def demo_home() -> FileResponse:
    demo_path = STATIC_DIR / "demo.html"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="demo page not found")
    return FileResponse(demo_path)


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


app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(confirm.router)
app.include_router(export.router)
app.include_router(metrics.router)
app.include_router(outbound.router)
app.include_router(transfers.router)
