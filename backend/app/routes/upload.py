from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlmodel import Session

from backend.app.auth import require_login
from backend.app.database import get_session
from backend.app.models import Category, Record, RecordStatus, User
from backend.app.schemas import BatchUploadJob, BatchUploadResponse, UploadResponse
from backend.app.services.dedup import find_duplicates, serialize_duplicates
from backend.app.services.file_storage import save_upload
from backend.app.services.normalize import normalize_label_value
from backend.app.workers.ocr_worker import run_ocr

router = APIRouter()


def get_ocr_runner():
    return run_ocr


def create_upload_job(
    *,
    background_tasks: BackgroundTasks,
    category: Category,
    vin_or_bin: str | None,
    serial_number: str | None,
    operator_id: str,
    file: UploadFile,
    session: Session,
    ocr_runner,
) -> tuple[Record, list]:
    normalized_vin = normalize_label_value(vin_or_bin)
    normalized_sn = normalize_label_value(serial_number)
    duplicates = find_duplicates(
        session,
        vin_or_bin=normalized_vin,
        serial_number=normalized_sn,
    )
    try:
        image_path = save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    record = Record(
        image_path=str(image_path),
        category=category,
        operator_id=(operator_id.strip() or "self")[:80],
        vin_or_bin=normalized_vin,
        serial_number=normalized_sn,
        status=RecordStatus.duplicate if duplicates else RecordStatus.uploaded,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    if not duplicates and record.id is not None:
        background_tasks.add_task(ocr_runner, record.id)
    return record, duplicates


@router.post("/upload", response_model=UploadResponse)
def upload_label(
    background_tasks: BackgroundTasks,
    category: Category = Form(...),
    vin_or_bin: str | None = Form(default=None),
    serial_number: str | None = Form(default=None),
    operator_id: str = Form(default="self"),
    file: UploadFile = File(...),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
    ocr_runner=Depends(get_ocr_runner),
) -> UploadResponse:
    record, duplicates = create_upload_job(
        background_tasks=background_tasks,
        category=category,
        vin_or_bin=vin_or_bin,
        serial_number=serial_number,
        operator_id=operator_id,
        file=file,
        session=session,
        ocr_runner=ocr_runner,
    )
    return UploadResponse(
        job_id=record.id or 0,
        status=record.status,
        barcodes=[],
        duplicates=serialize_duplicates(duplicates),
    )


@router.post("/upload/batch", response_model=BatchUploadResponse)
def upload_label_batch(
    background_tasks: BackgroundTasks,
    category: Category = Form(...),
    operator_id: str = Form(default="self"),
    files: list[UploadFile] = File(...),
    _: User = Depends(require_login),
    session: Session = Depends(get_session),
    ocr_runner=Depends(get_ocr_runner),
) -> BatchUploadResponse:
    jobs: list[BatchUploadJob] = []
    for file in files:
        record, duplicates = create_upload_job(
            background_tasks=background_tasks,
            category=category,
            vin_or_bin=None,
            serial_number=None,
            operator_id=operator_id,
            file=file,
            session=session,
            ocr_runner=ocr_runner,
        )
        jobs.append(
            BatchUploadJob(
                job_id=record.id or 0,
                filename=file.filename or "",
                status=record.status,
                barcodes=[],
                duplicates=serialize_duplicates(duplicates),
            )
        )
    return BatchUploadResponse(jobs=jobs)
