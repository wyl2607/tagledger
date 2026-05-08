from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import (
    EvidencePhoto,
    EvidencePhotoType,
    ReturnSignoffCandidate,
    ReturnSignoffStatus,
)


def test_return_signoff_candidate_defaults_and_status_transition(session: Session) -> None:
    candidate = ReturnSignoffCandidate(
        business_key="RETURN-ABC-123",
        return_reference="RMA-20260508-001",
        product_model="LUBA-2",
        serial_number="SN-LOCAL-001",
        captured_at=datetime(2026, 5, 8, 9, 30, tzinfo=UTC),
        confirmed_by="operator-a",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    assert candidate.id is not None
    assert candidate.status == ReturnSignoffStatus.draft
    assert candidate.factory_id == "factory_a"
    assert candidate.created_at is not None
    assert candidate.updated_at is not None

    candidate.status = ReturnSignoffStatus.ready_for_assist
    session.add(candidate)
    session.commit()

    stored = session.exec(
        select(ReturnSignoffCandidate).where(
            ReturnSignoffCandidate.business_key == "RETURN-ABC-123"
        )
    ).one()
    assert stored.status == ReturnSignoffStatus.ready_for_assist


def test_evidence_photo_links_to_local_candidate(session: Session) -> None:
    candidate = ReturnSignoffCandidate(business_key="RETURN-EVIDENCE-001")
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    assert candidate.id is not None

    photo = EvidencePhoto(
        candidate_id=candidate.id,
        source_record_id=42,
        photo_type=EvidencePhotoType.machine_label,
        storage_ref="data/uploads/2026/05/machine-label.jpg",
        ocr_text_summary="model LUBA-2, serial visible",
    )
    session.add(photo)
    session.commit()

    stored = session.exec(
        select(EvidencePhoto).where(EvidencePhoto.candidate_id == candidate.id)
    ).one()
    assert stored.photo_type == EvidencePhotoType.machine_label
    assert stored.capture_device == "phone"
    assert stored.storage_ref == "data/uploads/2026/05/machine-label.jpg"
    assert stored.updated_at is not None
