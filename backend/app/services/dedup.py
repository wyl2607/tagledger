from sqlmodel import Session, or_, select

from backend.app.models import Record, RecordStatus
from backend.app.schemas import DuplicateRecord
from backend.app.services.normalize import normalize_label_value


def find_duplicates(
    session: Session,
    *,
    vin_or_bin: str | None = None,
    serial_number: str | None = None,
    exclude_id: int | None = None,
) -> list[Record]:
    conditions = []
    normalized_vin = normalize_label_value(vin_or_bin)
    normalized_sn = normalize_label_value(serial_number)
    if normalized_vin:
        conditions.append(Record.vin_or_bin == normalized_vin)
    if normalized_sn:
        conditions.append(Record.serial_number == normalized_sn)
    if not conditions:
        return []

    statement = select(Record).where(or_(*conditions), Record.status != RecordStatus.duplicate)
    if exclude_id is not None:
        statement = statement.where(Record.id != exclude_id)
    return list(session.exec(statement).all())


def serialize_duplicates(records: list[Record]) -> list[DuplicateRecord]:
    return [
        DuplicateRecord(
            id=record.id or 0,
            model=record.model,
            vin_or_bin=record.vin_or_bin,
            serial_number=record.serial_number,
            status=record.status,
        )
        for record in records
    ]
