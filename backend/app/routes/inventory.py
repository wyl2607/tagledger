from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from backend.app.auth import require_login, require_supervisor
from backend.app.database import get_session
from backend.app.models import User
from backend.app.services.inventory_excel import parse_inventory_file_rows
from backend.app.services.inventory_service import (
    InventoryPermissionError,
    adjust_inventory_location,
    apply_inventory_reconcile,
    export_inventory_locations_csv,
    list_inventory_locations,
    move_inventory_quantity,
    preview_inventory_reconcile,
    recommend_inventory_picks,
)
from backend.app.services.location_map import build_inventory_location_map

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class InventoryLocationAdjustRequest(BaseModel):
    quantity: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=200)


class InventoryMoveRequest(BaseModel):
    source_location_id: int
    target_location_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(gt=0)
    target_location_kind: str = Field(default="temporary", max_length=40)
    reason: str = Field(min_length=1, max_length=200)


class InventoryReconcilePreviewRow(BaseModel):
    factory_id: str | None = Field(default=None, max_length=40)
    part_key: str = Field(min_length=1, max_length=80)
    location_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=0)


class InventoryReconcilePreviewRequest(BaseModel):
    rows: list[InventoryReconcilePreviewRow] = Field(default_factory=list)


class InventoryReconcileApplyDecision(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    decision: str = Field(min_length=1, max_length=40)
    factory_id: str | None = Field(default=None, max_length=40)
    part_key: str = Field(min_length=1, max_length=80)
    location_code: str = Field(min_length=1, max_length=80)
    system_quantity: int | None = Field(default=None, ge=0)
    excel_quantity: int | None = Field(default=None, ge=0)


class InventoryReconcileApplyRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    source_filename: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=1, max_length=200)
    decisions: list[InventoryReconcileApplyDecision] = Field(default_factory=list)


@router.get("/locations")
def get_inventory_locations(
    factory_id: str | None = None,
    part_key: str | None = None,
    include_hidden: bool = Query(default=False),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return list_inventory_locations(
            session=session,
            factory_id=factory_id,
            part_key=part_key,
            include_hidden=include_hidden,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/location-map")
def get_inventory_location_map(
    factory_id: str | None = None,
    include_hidden: bool = Query(default=False),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return build_inventory_location_map(
            session=session,
            factory_id=factory_id,
            include_hidden=include_hidden,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/pick-recommendations")
def get_inventory_pick_recommendations(
    part_key: str = Query(min_length=1, max_length=80),
    quantity: int = Query(gt=0),
    factory_id: str | None = Query(default=None),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return recommend_inventory_picks(
            session=session,
            part_key=part_key,
            quantity=quantity,
            factory_id=factory_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/export.csv")
def get_inventory_export_csv(
    _: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> Response:
    csv_text = export_inventory_locations_csv(session=session)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tagledger-inventory-current.csv"},
    )


@router.patch("/locations/{location_id}")
def patch_inventory_location(
    location_id: int,
    payload: InventoryLocationAdjustRequest,
    user: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return adjust_inventory_location(
            session=session,
            location_id=location_id,
            quantity=payload.quantity,
            reason=payload.reason,
            operator=user,
        )
    except RuntimeError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/move")
def post_inventory_move(
    payload: InventoryMoveRequest,
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return move_inventory_quantity(
            session=session,
            source_location_id=payload.source_location_id,
            target_location_code=payload.target_location_code,
            quantity=payload.quantity,
            target_location_kind=payload.target_location_kind,
            reason=payload.reason,
            operator=user,
        )
    except InventoryPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/reconcile/preview")
def post_inventory_reconcile_preview(
    payload: InventoryReconcilePreviewRequest,
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return preview_inventory_reconcile(
            session=session,
            rows=[row.model_dump() for row in payload.rows],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reconcile/apply")
def post_inventory_reconcile_apply(
    payload: InventoryReconcileApplyRequest,
    user: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return apply_inventory_reconcile(
            session=session,
            decisions=[decision.model_dump() for decision in payload.decisions],
            idempotency_key=payload.idempotency_key,
            source_filename=payload.source_filename,
            reason=payload.reason,
            operator=user,
        )
    except RuntimeError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/reconcile/preview-file")
async def post_inventory_reconcile_preview_file(
    file: UploadFile = File(...),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        rows = parse_inventory_file_rows(
            filename=file.filename or "",
            content=await file.read(),
        )
        payload = preview_inventory_reconcile(session=session, rows=rows)
        return {
            **payload,
            "filename": file.filename,
            "parsed_row_count": len(rows),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (UnicodeDecodeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail="invalid inventory file") from exc
