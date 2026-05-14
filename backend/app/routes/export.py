from datetime import date

from fastapi import APIRouter, Depends, Response
from fastapi.params import Query
from sqlmodel import Session

from backend.app.auth import require_login
from backend.app.database import get_session
from backend.app.models import RecordStatus, User
from backend.app.services.auth_service import has_role
from backend.app.services.export import export_records_csv_filtered

router = APIRouter()


@router.get("/export.csv")
def export_csv(
    status: list[RecordStatus] | None = Query(default=None),
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
) -> Response:
    csv_text = export_records_csv_filtered(
        session,
        statuses=status,
        operator_id=None if has_role(user, "supervisor") else user.username,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=records.csv"},
    )
