from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.config import ROOT_DIR
from backend.app.models import (
    Category,
    EvidencePhoto,
    Record,
    RecordStatus,
    ReturnSignoffCandidate,
    ReturnSignoffStatus,
)
from backend.app.services.auth_service import create_session, create_user
from backend.tests.conftest import set_authenticated_session


def _login_as_role(client: TestClient, session: Session, role: str) -> None:
    user = create_user(
        session,
        username=f"signoff-{role}",
        display_name=f"Signoff {role}",
        password=f"signoff-{role}-pass",
        role=role,
    )
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    set_authenticated_session(client, token)


def _confirmed_record(session: Session) -> Record:
    record = Record(
        image_path="data/uploads/signoff-machine-label.jpg",
        category=Category.A,
        model="LUBA-2",
        vin_or_bin="VIN-SIGNOFF-001",
        serial_number="SN-SIGNOFF-001",
        operator_id="operator-a",
        confidence_score=0.91,
        raw_ocr_text="model LUBA-2 serial SN-SIGNOFF-001",
        status=RecordStatus.confirmed,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_create_signoff_candidate_from_confirmed_record(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "supervisor")
    record = _confirmed_record(session)

    response = client.post(
        "/api/signoff/candidates",
        json={"record_id": record.id, "return_reference": "RMA-001", "notes": "ready"},
    )

    assert response.status_code == 201
    payload = response.json()
    candidate = payload["candidate"]
    assert candidate["status"] == ReturnSignoffStatus.ready_for_assist
    assert candidate["business_key"] == "RMA-001"
    assert candidate["product_model"] == "LUBA-2"
    assert candidate["serial_number"] == "SN-SIGNOFF-001"
    assert candidate["confirmed_by"] == "operator-a"

    evidence = payload["evidence_photos"][0]
    assert evidence["source_record_id"] == record.id
    assert evidence["storage_ref"] == "data/uploads/signoff-machine-label.jpg"

    stored_candidate = session.exec(select(ReturnSignoffCandidate)).one()
    stored_evidence = session.exec(select(EvidencePhoto)).one()
    assert stored_candidate.business_key == "RMA-001"
    assert stored_evidence.candidate_id == stored_candidate.id


def test_create_signoff_candidate_stores_relative_evidence_ref(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "supervisor")
    record = _confirmed_record(session)
    record.image_path = str(ROOT_DIR / "data/uploads/signoff-absolute.jpg")
    session.add(record)
    session.commit()

    response = client.post("/api/signoff/candidates", json={"record_id": record.id})

    assert response.status_code == 201
    payload = response.json()
    assert payload["evidence_photos"][0]["storage_ref"] == "data/uploads/signoff-absolute.jpg"
    assert str(ROOT_DIR) not in str(payload)


def test_create_signoff_candidate_rejects_duplicate_active_candidate(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "supervisor")
    record = _confirmed_record(session)

    first = client.post("/api/signoff/candidates", json={"record_id": record.id})
    assert first.status_code == 201

    second = client.post("/api/signoff/candidates", json={"record_id": record.id})
    assert second.status_code == 409


def test_list_signoff_candidates_filters_by_status(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "manager")
    session.add(
        ReturnSignoffCandidate(
            business_key="READY-1",
            status=ReturnSignoffStatus.ready_for_assist,
        )
    )
    session.add(
        ReturnSignoffCandidate(
            business_key="DRAFT-1",
            status=ReturnSignoffStatus.draft,
        )
    )
    session.commit()

    response = client.get("/api/signoff/candidates?status=ready_for_assist")

    assert response.status_code == 200
    payload = response.json()
    assert [item["business_key"] for item in payload["candidates"]] == ["READY-1"]
    assert payload["total"] == 1


def test_get_signoff_candidate_detail_includes_evidence(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "manager")
    record = _confirmed_record(session)
    created = client.post("/api/signoff/candidates", json={"record_id": record.id})
    candidate_id = created.json()["candidate"]["id"]

    response = client.get(f"/api/signoff/candidates/{candidate_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["id"] == candidate_id
    assert payload["evidence_photos"][0]["source_record_id"] == record.id


def test_signoff_api_rejects_operator_and_anonymous(
    client: TestClient,
    session: Session,
) -> None:
    record = _confirmed_record(session)

    assert client.get("/api/signoff/candidates").status_code == 401

    _login_as_role(client, session, "operator")
    assert client.get("/api/signoff/candidates").status_code == 403
    response = client.post("/api/signoff/candidates", json={"record_id": record.id})
    assert response.status_code == 403


def test_create_signoff_candidate_requires_confirmed_record(
    client: TestClient,
    session: Session,
) -> None:
    _login_as_role(client, session, "supervisor")
    record = Record(
        image_path="data/uploads/unconfirmed.jpg",
        category=Category.A,
        model="LUBA-2",
        status=RecordStatus.ocr_done,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    response = client.post("/api/signoff/candidates", json={"record_id": record.id})

    assert response.status_code == 409
