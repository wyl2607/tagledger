from datetime import date

from fastapi import APIRouter, Depends, Response
from fastapi.params import Query
from sqlmodel import Session

from backend.app.database import get_session
from backend.app.models import RecordStatus
from backend.app.services.export import export_records_csv_filtered

router = APIRouter()


@router.get("/export.csv")
def export_csv(
    status: list[RecordStatus] | None = Query(default=None),
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    session: Session = Depends(get_session),
) -> Response:
    csv_text = export_records_csv_filtered(
        session,
        statuses=status,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=records.csv"},
    )
