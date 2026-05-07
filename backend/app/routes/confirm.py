from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from backend.app.auth import require_login
from backend.app.config import get_settings
from backend.app.database import get_session
from backend.app.models import Record, RecordStatus, User, utc_now
from backend.app.schemas import ConfirmRequest, ConfirmResponse
from backend.app.services.dedup import find_duplicates, serialize_duplicates
from backend.app.workers.submit_worker import run as run_submit_worker

router = APIRouter()


def get_submit_runner():
    return run_submit_worker


@router.post("/confirm/{record_id}", response_model=ConfirmResponse)
def confirm_record(
    record_id: int,
    payload: ConfirmRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
    submit_runner=Depends(get_submit_runner),
) -> ConfirmResponse:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")

    next_vin = payload.vin_or_bin if payload.vin_or_bin is not None else record.vin_or_bin
    next_sn = payload.serial_number if payload.serial_number is not None else record.serial_number
    duplicates = find_duplicates(
        session,
        vin_or_bin=next_vin,
        serial_number=next_sn,
        exclude_id=record.id,
    )
    if duplicates and payload.duplicate_action == "abandon":
        record.status = RecordStatus.duplicate
        record.updated_at = utc_now()
        session.add(record)
        session.commit()
        return ConfirmResponse(
            id=record.id or 0,
            status=record.status,
            duplicates=serialize_duplicates(duplicates),
        )

    if duplicates and payload.duplicate_action == "overwrite":
        for duplicate in duplicates:
            duplicate.vin_or_bin = None
            duplicate.serial_number = None
            duplicate.status = RecordStatus.duplicate
            duplicate.updated_at = utc_now()
            session.add(duplicate)

    if payload.category is not None:
        record.category = payload.category
    if payload.model is not None:
        record.model = payload.model
    record.vin_or_bin = next_vin
    record.serial_number = next_sn
    record.status = RecordStatus.confirmed
    record.updated_at = utc_now()
    session.add(record)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="duplicate VIN/BIN or serial number") from exc
    if record.id is not None and get_settings().enable_saas_submit:
        background_tasks.add_task(submit_runner, record.id)
    return ConfirmResponse(id=record.id or 0, status=record.status, duplicates=[])
