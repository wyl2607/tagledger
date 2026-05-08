from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from backend.app.auth import require_supervisor
from backend.app.config import ROOT_DIR
from backend.app.database import get_session
from backend.app.models import (
    EvidencePhoto,
    EvidencePhotoType,
    Record,
    RecordStatus,
    ReturnSignoffCandidate,
    ReturnSignoffStatus,
    User,
)

router = APIRouter(prefix="/api/signoff", tags=["signoff"])


class SignoffCandidateCreateRequest(BaseModel):
    record_id: int
    business_key: str | None = Field(default=None, max_length=160)
    return_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


def _candidate_payload(candidate: ReturnSignoffCandidate) -> dict[str, object]:
    return {
        "id": candidate.id or 0,
        "factory_id": candidate.factory_id,
        "status": candidate.status.value,
        "business_key": candidate.business_key,
        "return_reference": candidate.return_reference,
        "product_model": candidate.product_model,
        "serial_number": candidate.serial_number,
        "captured_at": candidate.captured_at.isoformat() if candidate.captured_at else None,
        "confirmed_by": candidate.confirmed_by,
        "notes": candidate.notes,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


def _evidence_payload(photo: EvidencePhoto) -> dict[str, object]:
    return {
        "id": photo.id or 0,
        "candidate_id": photo.candidate_id,
        "source_record_id": photo.source_record_id,
        "photo_type": photo.photo_type.value,
        "storage_ref": photo.storage_ref,
        "capture_device": photo.capture_device,
        "created_at": photo.created_at.isoformat(),
        "updated_at": photo.updated_at.isoformat(),
    }


def _candidate_with_evidence_payload(
    candidate: ReturnSignoffCandidate,
    evidence_photos: list[EvidencePhoto],
) -> dict[str, object]:
    return {
        "candidate": _candidate_payload(candidate),
        "evidence_photos": [_evidence_payload(photo) for photo in evidence_photos],
    }


def _business_key_from_record(
    record: Record,
    explicit_business_key: str | None,
    return_reference: str | None,
) -> str:
    for value in (
        explicit_business_key,
        return_reference,
        record.serial_number,
        record.vin_or_bin,
        record.model,
    ):
        normalized = (value or "").strip()
        if normalized:
            return normalized
    raise HTTPException(
        status_code=422,
        detail="record needs a business key, return reference, serial number, VIN/BIN, or model",
    )


def _storage_ref_from_record(record: Record) -> str:
    image_path = Path(record.image_path)
    try:
        return image_path.resolve().relative_to(ROOT_DIR).as_posix()
    except (OSError, ValueError):
        return image_path.name


def _active_candidate_for_record(session: Session, record_id: int) -> ReturnSignoffCandidate | None:
    evidence_rows = session.exec(
        select(EvidencePhoto).where(EvidencePhoto.source_record_id == record_id)
    ).all()
    candidate_ids = [row.candidate_id for row in evidence_rows]
    if not candidate_ids:
        return None
    return session.exec(
        select(ReturnSignoffCandidate)
        .where(ReturnSignoffCandidate.id.in_(candidate_ids))  # type: ignore[attr-defined]
        .where(
            ReturnSignoffCandidate.status.not_in(  # type: ignore[attr-defined]
                [ReturnSignoffStatus.manually_completed, ReturnSignoffStatus.needs_review]
            )
        )
        .order_by(ReturnSignoffCandidate.id.desc())
    ).first()


@router.post("/candidates", status_code=201)
def create_signoff_candidate(
    payload: SignoffCandidateCreateRequest,
    user: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    record = session.get(Record, payload.record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    if record.status != RecordStatus.confirmed:
        raise HTTPException(
            status_code=409,
            detail=f"record status is {record.status}, only confirmed records can start sign-off",
        )
    existing = _active_candidate_for_record(session, record.id or 0)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"record already has active sign-off candidate {existing.id}",
        )

    business_key = _business_key_from_record(
        record,
        payload.business_key,
        payload.return_reference,
    )
    now = datetime.now(record.updated_at.tzinfo)
    candidate = ReturnSignoffCandidate(
        factory_id=record.factory_id,
        status=ReturnSignoffStatus.ready_for_assist,
        business_key=business_key,
        return_reference=payload.return_reference,
        product_model=record.model,
        serial_number=record.serial_number,
        captured_at=record.updated_at,
        confirmed_by=record.operator_id or user.username,
        ocr_confidence_summary=(
            f"{record.confidence_score:.3f}" if record.confidence_score is not None else None
        ),
        notes=payload.notes,
        updated_at=now,
    )
    session.add(candidate)
    session.flush()
    session.refresh(candidate)

    evidence = EvidencePhoto(
        factory_id=record.factory_id,
        candidate_id=candidate.id or 0,
        source_record_id=record.id,
        photo_type=EvidencePhotoType.machine_label,
        storage_ref=_storage_ref_from_record(record),
        ocr_text_summary=record.raw_ocr_text,
        updated_at=now,
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)

    return _candidate_with_evidence_payload(candidate, [evidence])


@router.get("/candidates")
def list_signoff_candidates(
    status: ReturnSignoffStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(ReturnSignoffCandidate).order_by(ReturnSignoffCandidate.id.desc())
    if status is not None:
        statement = statement.where(ReturnSignoffCandidate.status == status)
    count_statement = select(func.count()).select_from(ReturnSignoffCandidate)
    if status is not None:
        count_statement = count_statement.where(ReturnSignoffCandidate.status == status)
    candidates = session.exec(statement.offset(offset).limit(limit)).all()
    return {
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
        "total": session.exec(count_statement).one() or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/candidates/{candidate_id}")
def get_signoff_candidate(
    candidate_id: int,
    _: User = Depends(require_supervisor),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    candidate = session.get(ReturnSignoffCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    evidence_photos = session.exec(
        select(EvidencePhoto)
        .where(EvidencePhoto.candidate_id == candidate_id)
        .order_by(EvidencePhoto.id)
    ).all()
    return _candidate_with_evidence_payload(candidate, evidence_photos)
