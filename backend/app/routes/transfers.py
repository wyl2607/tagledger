from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from backend.app.auth import require_supervisor
from backend.app.database import get_session
from backend.app.models import User
from backend.app.services.transfer_service import (
    create_transfer,
    factory_summary_report,
    list_transfers,
)

router = APIRouter()


class TransferCreateRequest(BaseModel):
    source_factory: str
    target_factory: str
    part_key: str
    quantity: int = Field(gt=0)
    reason: str


@router.post("/api/transfers")
def post_transfer(
    payload: TransferCreateRequest,
    user: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return create_transfer(
            source_factory=payload.source_factory,
            target_factory=payload.target_factory,
            part_key=payload.part_key,
            quantity=payload.quantity,
            reason=payload.reason,
            operator=user,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/transfers")
def get_transfers(
    factory_id: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=500),
    _: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return list_transfers(
            session=session,
            factory_id=factory_id,
            days=days,
            limit=limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/reports/factory-summary")
def get_factory_summary(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    _: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        from_at = datetime.fromisoformat(from_) if from_ else None
        to_at = datetime.fromisoformat(to) if to else None
        return factory_summary_report(session=session, from_at=from_at, to_at=to_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid datetime: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
