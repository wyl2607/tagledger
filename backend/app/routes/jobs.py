import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from backend.app.database import get_session
from backend.app.models import Record, RecordStatus
from backend.app.schemas import RecordListItem, RecordRead, RetryResponse
from backend.app.services.dedup import find_duplicates, serialize_duplicates
from backend.app.workers.submit_worker import enqueue_submission


router = APIRouter()


def record_barcodes(record: Record) -> list[dict[str, str]]:
    if not record.barcodes_json:
        return []
    try:
        payload = json.loads(record.barcodes_json)
    except json.JSONDecodeError:
        return []
    return [
        {"type": str(item.get("type", "")), "data": str(item.get("data", ""))}
        for item in payload
        if isinstance(item, dict) and item.get("data")
    ]


def to_record_list_item(record: Record) -> RecordListItem:
    return RecordListItem(
        id=record.id or 0,
        image_path=record.image_path,
        category=record.category,
        model=record.model,
        vin_or_bin=record.vin_or_bin,
        serial_number=record.serial_number,
        confidence_score=record.confidence_score,
        status=record.status,
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/jobs", response_model=list[RecordListItem])
def list_jobs(
    status: RecordStatus | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[RecordListItem]:
    statement = select(Record).order_by(Record.id.desc()).offset(offset).limit(limit)
    if status is not None:
        statement = statement.where(Record.status == status)
    records = session.exec(statement).all()
    return [to_record_list_item(record) for record in records]


@router.get("/jobs/{record_id}", response_model=RecordRead)
def get_job(record_id: int, session: Session = Depends(get_session)) -> RecordRead:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    duplicates = find_duplicates(
        session,
        vin_or_bin=record.vin_or_bin,
        serial_number=record.serial_number,
        exclude_id=record.id,
    )
    return RecordRead(
        id=record.id or 0,
        image_path=record.image_path,
        category=record.category,
        model=record.model,
        vin_or_bin=record.vin_or_bin,
        serial_number=record.serial_number,
        raw_ocr_text=record.raw_ocr_text,
        confidence_score=record.confidence_score,
        status=record.status,
        last_error=record.last_error,
        barcodes=record_barcodes(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
        duplicates=serialize_duplicates(duplicates),
    )


@router.get("/records/{record_id}/image", include_in_schema=False)
def get_record_image(record_id: int, session: Session = Depends(get_session)) -> FileResponse:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    image_path = Path(record.image_path)
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(image_path)


@router.post("/jobs/retry/{record_id}", response_model=RetryResponse)
def retry_submission(
    record_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RetryResponse:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    if record.status not in (RecordStatus.submission_failed, RecordStatus.confirmed):
        raise HTTPException(
            status_code=409,
            detail=f"record status is {record.status}, only submission_failed or confirmed can be retried",
        )
    record.submission_attempts = 0
    record.last_error = None
    record.error_screenshot = None
    record.status = RecordStatus.confirmed
    session.add(record)
    session.commit()
    if record.id is not None:
        background_tasks.add_task(enqueue_submission, record.id)
    return RetryResponse(id=record.id or 0, status=record.status)


@router.post("/jobs/retry", response_model=list[RetryResponse])
def retry_all_failed(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> list[RetryResponse]:
    records = session.exec(
        select(Record).where(Record.status == RecordStatus.submission_failed)
    ).all()
    results: list[RetryResponse] = []
    for record in records:
        record.submission_attempts = 0
        record.last_error = None
        record.error_screenshot = None
        record.status = RecordStatus.confirmed
        session.add(record)
        results.append(RetryResponse(id=record.id or 0, status=record.status))
    session.commit()
    for result in results:
        background_tasks.add_task(enqueue_submission, result.id)
    return results
