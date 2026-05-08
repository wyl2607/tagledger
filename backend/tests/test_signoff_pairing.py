from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import (
    Category,
    EvidencePhoto,
    Record,
    RecordStatus,
    ReturnSignoffCandidate,
    ReturnSignoffStatus,
    SignoffAssistSession,
    SignoffPairingKey,
    SignoffPairingKeyStatus,
)
from backend.app.routes.signoff import _hash_token
from backend.app.services.auth_service import create_session, create_user
from backend.tests.conftest import set_authenticated_session


def _login_supervisor(client: TestClient, session: Session) -> None:
    user = create_user(
        session,
        username="pairing-supervisor",
        display_name="Pairing Supervisor",
        password="pairing-supervisor-pass",
        role="supervisor",
    )
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    set_authenticated_session(client, token)


def _signoff_candidate(client: TestClient, session: Session) -> int:
    record = Record(
        image_path="data/uploads/pairing-machine-label.jpg",
        category=Category.A,
        model="LUBA-2",
        serial_number="SN-PAIRING-001",
        operator_id="operator-pairing",
        confidence_score=0.88,
        raw_ocr_text="raw OCR text should stay out of preview",
        status=RecordStatus.confirmed,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    response = client.post("/api/signoff/candidates", json={"record_id": record.id})
    assert response.status_code == 201
    return int(response.json()["candidate"]["id"])


def test_pairing_key_returns_plain_token_once_and_stores_hash(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/pairing-keys",
        json={"ttl_minutes": 15},
    )

    assert response.status_code == 201
    payload = response.json()
    token = payload["token"]
    assert token
    assert payload["preview_url"].endswith(f"/assist/{token}/preview")

    stored = session.exec(select(SignoffPairingKey)).one()
    assert stored.token_hash == _hash_token(token)
    assert token not in str(stored)
    assert stored.status == SignoffPairingKeyStatus.active


def test_pairing_preview_returns_sanitized_payload_and_records_session(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    client.cookies.clear()
    client.headers.clear()

    response = client.get(f"/api/signoff/assist/{token}/preview")

    assert response.status_code == 200
    payload = response.json()
    preview = payload["payload"]
    assert preview["mode"] == "dry_run"
    assert preview["manual_completion_required"] is True
    assert preview["candidate"]["serial_number"] == "SN-PAIRING-001"
    assert preview["evidence_photos"][0]["storage_ref"] == "data/uploads/pairing-machine-label.jpg"
    assert "raw OCR text" not in str(payload)
    assert "prepared_payload_hash" in payload

    stored_session = session.exec(select(SignoffAssistSession)).one()
    assert stored_session.prepared_payload_hash == payload["prepared_payload_hash"]
    candidate = session.get(ReturnSignoffCandidate, candidate_id)
    assert candidate is not None
    assert candidate.status == ReturnSignoffStatus.assist_previewed


def test_pairing_preview_rejects_expired_or_unknown_token(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = "expired-token"
    session.add(
        SignoffPairingKey(
            candidate_id=candidate_id,
            token_hash=_hash_token(token),
            expires_at=datetime(2000, 1, 1),
        )
    )
    session.commit()

    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 404
    assert client.get("/api/signoff/assist/not-a-token/preview").status_code == 404


def test_pairing_key_requires_supervisor(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    client.cookies.clear()
    client.headers.clear()

    assert client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").status_code == 403

    operator = create_user(
        session,
        username="pairing-operator",
        display_name="Pairing Operator",
        password="pairing-operator-pass",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    set_authenticated_session(client, token)

    assert client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").status_code == 403


def test_pairing_preview_uses_relative_storage_ref(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    evidence = session.exec(select(EvidencePhoto)).one()
    evidence.storage_ref = "/Users/yumei/private/absolute.jpg"
    session.add(evidence)
    session.commit()
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]

    response = client.get(f"/api/signoff/assist/{token}/preview")

    assert response.status_code == 200
    assert "/Users/yumei" not in str(response.json())
