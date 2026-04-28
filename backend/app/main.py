from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.app.config import get_settings
from backend.app.database import create_db_and_tables
from backend.app.routes import confirm, export, jobs, upload
from backend.app.workers.submit_worker import enqueue_pending_confirmed


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    enqueue_pending_confirmed()
    yield


app = FastAPI(title="Machine Label OCR", version="0.1.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/runtime/status")
def runtime_status() -> dict[str, bool | str]:
    settings = get_settings()
    return {
        "ocr_provider": settings.ocr_provider,
        "enable_barcode": settings.enable_barcode,
        "enable_saas_submit": settings.enable_saas_submit,
        "dry_run": settings.dry_run,
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


app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(confirm.router)
app.include_router(export.router)
