from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from backend.app.auth import require_login, require_supervisor
from backend.app.database import get_session
from backend.app.models import User
from backend.app.services.inventory_service import (
    adjust_inventory_location,
    list_inventory_locations,
    move_inventory_quantity,
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
    except RuntimeError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
