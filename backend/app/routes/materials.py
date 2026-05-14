from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.app.auth import require_login, require_supervisor
from backend.app.config import get_settings
from backend.app.models import User
from backend.app.services.material_mapping import (
    clear_material_mapping_cache,
    load_material_matches,
    material_catalog,
    material_match_to_dict,
    search_material_catalog,
)

router = APIRouter(prefix="/api/materials")


def _material_file_path() -> Path:
    return get_settings().material_mapping_file


@router.get("/catalog")
def list_material_catalog(
    q: str = "",
    limit: int | None = None,
    _: User = Depends(require_login),
) -> dict[str, object]:
    rows = search_material_catalog(q, limit=limit)
    total = len(material_catalog())
    return {
        "items": [material_match_to_dict(row) for row in rows],
        "count": len(rows),
        "total": total,
        "query": q,
    }


@router.post("/catalog/import", status_code=status.HTTP_201_CREATED)
async def import_material_catalog(
    file: UploadFile = File(...),
    _: User = Depends(require_supervisor),
) -> dict[str, object]:
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=415, detail="only .xlsx or .xlsm files are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty material mapping file")
    target = _material_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    clear_material_mapping_cache()
    rows = load_material_matches(target)
    return {"ok": True, "count": len(rows)}
