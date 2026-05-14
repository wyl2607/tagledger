import csv
from datetime import date, datetime, time
from io import StringIO

from sqlalchemy import or_
from sqlmodel import Session, select

from backend.app.models import Record, RecordStatus

CSV_FIELDS = [
    "id",
    "category",
    "model",
    "vin_or_bin",
    "serial_number",
    "status",
    "image_path",
    "confidence_score",
    "created_at",
    "updated_at",
]

DANGEROUS_CSV_PREFIXES = {"=", "+", "-", "@"}


def _sanitize_csv_cell(value: object) -> object:
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if stripped and stripped[0] in DANGEROUS_CSV_PREFIXES:
        return f"'{value}"
    return value


def export_records_csv(session: Session, status: RecordStatus | None = None) -> str:
    statuses = [status] if status is not None else None
    return export_records_csv_filtered(session, statuses=statuses)


def export_records_csv_filtered(
    session: Session,
    *,
    statuses: list[RecordStatus] | None = None,
    operator_id: str | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> str:
    statement = select(Record).order_by(Record.id)
    if statuses:
        statement = statement.where(Record.status.in_(statuses))
    if operator_id:
        statement = statement.where(Record.operator_id == operator_id)
    cleaned_keyword = keyword.strip().upper() if keyword else None
    if cleaned_keyword:
        like_term = f"%{cleaned_keyword}%"
        statement = statement.where(
            or_(
                Record.model.ilike(like_term),
                Record.vin_or_bin.ilike(like_term),
                Record.serial_number.ilike(like_term),
            )
        )
    if date_from is not None:
        statement = statement.where(Record.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        statement = statement.where(Record.created_at <= datetime.combine(date_to, time.max))
    records = session.exec(statement).all()
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for record in records:
        writer.writerow({field: _sanitize_csv_cell(getattr(record, field)) for field in CSV_FIELDS})
    return buffer.getvalue()
