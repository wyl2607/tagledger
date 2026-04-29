from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.outbound_reconciliation import outbound_summary, query_outbound

router = APIRouter(prefix="/api/outbound")


@router.get("/summary")
def get_outbound_summary() -> dict[str, object]:
    try:
        return outbound_summary()
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
