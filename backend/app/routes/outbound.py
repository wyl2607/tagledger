from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlmodel import Session

from backend.app.auth import current_user_optional, require_login, require_supervisor
from backend.app.database import get_session
from backend.app.models import User
from backend.app.schemas import (
    OutboundCurrentOrderPreferenceRead,
    OutboundCurrentOrderPreferenceWrite,
)
from backend.app.services.outbound_reconciliation import (
    OutboundVerificationRequiredError,
    complete_outbound_order,
    get_inventory_locations,
    get_inventory_movements,
    inbound_inventory,
    normalize_order_no,
    outbound_batch_detail,
    outbound_ops_health,
    outbound_order_choices,
    outbound_order_scans,
    outbound_order_status,
    outbound_orders_overview,
    outbound_orders_status,
    outbound_progress_snapshots,
    outbound_remaining_csv,
    outbound_summary,
    preview_outbound_scan,
    query_outbound,
    register_outbound_scan,
    rollback_outbound_order,
    set_inventory_location_status,
    set_outbound_part_quantity,
    sync_outbound_completion_marks,
    void_outbound_batch,
    void_outbound_scan,
)

router = APIRouter(prefix="/api/outbound")


class OutboundScanRequest(BaseModel):
    order_no: str
    code: str
    operator_id: str = "self"
    record_id: int | None = None
    verification_record_id: int | None = None
    quantity: int = 1
    location_code: str | None = None


class InboundInventoryRequest(BaseModel):
    part_key: str
    location_code: str
    quantity: int
    operator_id: str = "self"
    reason: str = "inbound"


class InventoryLocationStatusRequest(BaseModel):
    part_key: str
    location_code: str
    status: str
    operator_id: str = "self"
    reason: str = "location_status"
    replacement_location_code: str | None = None


class OutboundVoidRequest(BaseModel):
    operator_id: str = "self"
    reason: str = "operator_void"


class OutboundPartQuantityRequest(BaseModel):
    part_key: str
    quantity: int
    operator_id: str = "self"
    reason: str = "manual_set"
    batch_id: str | None = None


class OutboundOrderCompleteRequest(BaseModel):
    operator_id: str = "self"


class OutboundOrderRollbackRequest(BaseModel):
    operator_id: str = "self"


class OutboundCompletionMarkSyncRequest(BaseModel):
    text: str
    order_no: str | None = None
    operator_id: str = "self"


class OutboundBatchVoidRequest(BaseModel):
    operator_id: str = "self"


def _fallback_order_no(orders: list[str]) -> str | None:
    cleaned = [normalize_order_no(order) for order in orders if normalize_order_no(order)]
    if not cleaned:
        return None
    return sorted(cleaned)[-1]


@router.get("/summary")
def get_outbound_summary(_: object = Depends(require_login)) -> dict[str, object]:
    try:
        return outbound_summary()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ops-health")
def get_outbound_ops_health(
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_ops_health(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders")
def get_outbound_order_choices(_: object = Depends(require_login)) -> dict[str, object]:
    try:
        return outbound_order_choices()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/preferences/current-order", response_model=OutboundCurrentOrderPreferenceRead)
def post_outbound_current_order_preference(
    payload: OutboundCurrentOrderPreferenceWrite,
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> OutboundCurrentOrderPreferenceRead:
    order_no = normalize_order_no(payload.order_no)
    if not order_no:
        raise HTTPException(status_code=422, detail="order_no is required")
    user.outbound_last_order_no = order_no
    session.add(user)
    session.commit()
    session.refresh(user)
    return OutboundCurrentOrderPreferenceRead(
        selected_order_no=order_no,
        saved_order_no=order_no,
        fallback=False,
        reason=None,
    )


@router.get("/preferences/current-order", response_model=OutboundCurrentOrderPreferenceRead)
def get_outbound_current_order_preference(
    user: User = Depends(require_login),
) -> OutboundCurrentOrderPreferenceRead:
    choices = outbound_order_choices()
    available_orders = [
        normalize_order_no(v) for v in choices.get("order_numbers", {}).get("shipping", [])
    ]
    available = [value for value in available_orders if value]
    saved = normalize_order_no(user.outbound_last_order_no or "")
    if saved and saved in available:
        return OutboundCurrentOrderPreferenceRead(
            selected_order_no=saved,
            saved_order_no=saved,
            fallback=False,
            reason=None,
        )
    fallback = _fallback_order_no(available)
    reason = (
        "saved_order_not_available"
        if saved and fallback
        else ("no_orders_available" if not fallback else "no_saved_order")
    )
    return OutboundCurrentOrderPreferenceRead(
        selected_order_no=fallback,
        saved_order_no=saved or None,
        fallback=bool(saved and fallback and fallback != saved),
        reason=reason,
    )


@router.post("/inventory/inbound")
def post_inbound_inventory(
    payload: InboundInventoryRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return inbound_inventory(
            part_key=payload.part_key,
            location_code=payload.location_code,
            quantity=payload.quantity,
            operator_id=payload.operator_id,
            reason=payload.reason,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/inventory/locations")
def get_outbound_inventory_locations(
    part_key: str | None = None,
    status: str | None = None,
    exclude_temporary: bool = False,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return get_inventory_locations(
        session,
        part_key=part_key,
        status=status,
        exclude_temporary=exclude_temporary,
    )


@router.get("/inventory/movements")
def get_outbound_inventory_movements(
    part_key: str | None = None,
    location_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return get_inventory_movements(
        session,
        part_key=part_key,
        location_code=location_code,
        limit=limit,
    )


@router.post("/inventory/location-status")
def post_outbound_inventory_location_status(
    payload: InventoryLocationStatusRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return set_inventory_location_status(
            part_key=payload.part_key,
            location_code=payload.location_code,
            status=payload.status,
            operator_id=payload.operator_id,
            reason=payload.reason,
            replacement_location_code=payload.replacement_location_code,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/query")
def get_outbound_query(
    code: str = Query(..., min_length=1),
    order_no: Annotated[list[str] | None, Query()] = None,
) -> dict[str, object]:
    try:
        return query_outbound(code, selected_orders=order_no)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/{order_no}/status")
def get_outbound_order_status(
    order_no: str,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_order_status(order_no, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/{order_no}/scans")
def get_outbound_order_scans(
    order_no: str,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_order_scans(order_no, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/{order_no}/remaining.csv")
def get_outbound_remaining_csv(
    order_no: str,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> Response:
    try:
        csv_text = outbound_remaining_csv(order_no, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    filename = f"{normalize_order_no(order_no)}-remaining.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/progress-snapshots")
def get_outbound_progress_snapshots(
    order_no: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_progress_snapshots(order_no, session, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/orders/{order_no}/batches/{batch_id}/void")
def post_outbound_batch_void(
    order_no: str,
    batch_id: str,
    payload: OutboundBatchVoidRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return void_outbound_batch(
            order_no=order_no,
            batch_id=batch_id,
            operator_id=payload.operator_id,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders/{order_no}/batches/{batch_id}")
def get_outbound_batch_detail(
    order_no: str,
    batch_id: str,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_batch_detail(order_no, batch_id, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders/{order_no}/parts/set-quantity")
def post_outbound_part_quantity(
    order_no: str,
    payload: OutboundPartQuantityRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return set_outbound_part_quantity(
            order_no=order_no,
            part_key=payload.part_key,
            quantity=payload.quantity,
            operator_id=payload.operator_id,
            reason=payload.reason,
            batch_id=payload.batch_id,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/orders/{order_no}/complete")
def post_outbound_order_complete(
    order_no: str,
    payload: OutboundOrderCompleteRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return complete_outbound_order(
            order_no=order_no,
            operator_id=payload.operator_id,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/orders/{order_no}/rollback")
def post_outbound_order_rollback(
    order_no: str,
    payload: OutboundOrderRollbackRequest,
    user: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return rollback_outbound_order(
            order_no=order_no,
            operator=user,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/status")
def get_outbound_orders_status(
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_orders_status(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/overview")
def get_outbound_orders_overview(
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return outbound_orders_overview(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/scan")
def post_outbound_scan(
    payload: OutboundScanRequest,
    user: object | None = Depends(current_user_optional),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return register_outbound_scan(
            order_no=payload.order_no,
            code=payload.code,
            operator_id=getattr(user, "username", None)
            if user is not None
            else payload.operator_id,
            record_id=payload.record_id,
            verification_record_id=payload.verification_record_id,
            quantity=payload.quantity,
            location_code=payload.location_code,
            session=session,
        )
    except OutboundVerificationRequiredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/scan/preview")
def post_outbound_scan_preview(
    payload: OutboundScanRequest,
    _: object = Depends(require_login),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        preview_payload = preview_outbound_scan(
            order_no=payload.order_no,
            code=payload.code,
            operator_id=payload.operator_id,
            record_id=payload.record_id,
            verification_record_id=payload.verification_record_id,
            quantity=payload.quantity,
            location_code=payload.location_code,
            session=session,
        )
        return preview_payload
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/completion-marks/sync")
def post_outbound_completion_marks_sync(
    payload: OutboundCompletionMarkSyncRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return sync_outbound_completion_marks(
            text=payload.text,
            order_no=payload.order_no,
            operator_id=payload.operator_id,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/scans/{scan_id}/void")
def post_outbound_scan_void(
    scan_id: int,
    payload: OutboundVoidRequest,
    _: None = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return void_outbound_scan(
            scan_id=scan_id,
            operator_id=payload.operator_id,
            reason=payload.reason,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
