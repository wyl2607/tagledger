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
    stored_key = session.exec(select(SignoffPairingKey)).one()
    assert stored_key.preview_count == 1
    assert stored_key.last_previewed_at is not None


def test_pairing_preview_rate_limits_same_key(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    client.cookies.clear()
    client.headers.clear()

    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200
    second = client.get(f"/api/signoff/assist/{token}/preview")

    assert second.status_code == 429
    assert second.json()["detail"] == "pairing key preview rate limit exceeded"


def test_pairing_preview_is_exempt_from_device_pairing(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    import backend.app.middleware.lan_guard as lan_guard
    from backend.app.config import get_settings

    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    client.cookies.clear()
    client.headers.clear()

    monkeypatch.setattr(get_settings(), "pairing_enabled", True)
    monkeypatch.setattr(lan_guard, "_get_remote_ip", lambda _request: "10.9.8.7")

    response = client.get(f"/api/signoff/assist/{token}/preview", headers={"Host": "localhost"})

    assert response.status_code == 200
    assert response.json()["payload"]["candidate"]["serial_number"] == "SN-PAIRING-001"


def test_pairing_preview_reuses_open_assist_session(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200

    pairing_key = session.exec(select(SignoffPairingKey)).one()
    pairing_key.last_previewed_at = None
    session.add(pairing_key)
    session.commit()

    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200
    assert len(session.exec(select(SignoffAssistSession)).all()) == 1
    assert session.exec(select(SignoffPairingKey)).one().preview_count == 2


def test_repeated_pairing_preview_cannot_be_signed_off_twice(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200

    pairing_key = session.exec(select(SignoffPairingKey)).one()
    pairing_key.last_previewed_at = None
    session.add(pairing_key)
    session.commit()

    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200
    first = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "accepted"},
    )
    second = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "manually_completed"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    stored_sessions = session.exec(select(SignoffAssistSession)).all()
    assert len(stored_sessions) == 1
    assert stored_sessions[0].operator_decision == "accepted"


def test_pairing_key_can_be_revoked_by_supervisor(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    created = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys")
    token = created.json()["token"]
    pairing_key_id = created.json()["pairing_key_id"]

    response = client.post(f"/api/signoff/pairing-keys/{pairing_key_id}/revoke")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pairing_key"]["status"] == SignoffPairingKeyStatus.revoked
    assert payload["pairing_key"]["revoked_at"] is not None
    stored = session.get(SignoffPairingKey, pairing_key_id)
    assert stored is not None
    assert stored.status == SignoffPairingKeyStatus.revoked
    client.cookies.clear()
    client.headers.clear()
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 404


def test_pairing_key_revoke_requires_supervisor(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    pairing_key_id = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()[
        "pairing_key_id"
    ]
    client.cookies.clear()
    client.headers.clear()

    assert client.post(f"/api/signoff/pairing-keys/{pairing_key_id}/revoke").status_code == 403


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
    evidence.storage_ref = "/var/tmp/tagledger-private/absolute.jpg"
    session.add(evidence)
    session.commit()
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]

    response = client.get(f"/api/signoff/assist/{token}/preview")

    assert response.status_code == 200
    assert "/var/tmp/tagledger-private" not in str(response.json())


def test_signoff_decision_marks_candidate_manually_completed(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    preview = client.get(f"/api/signoff/assist/{token}/preview")
    assert preview.status_code == 200

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={
            "decision": "manually_completed",
            "external_completion_mark": "operator confirmed external save",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["status"] == ReturnSignoffStatus.manually_completed
    assert payload["assist_session"]["operator_decision"] == "manually_completed"
    assert (
        payload["assist_session"]["external_completion_mark"] == "operator confirmed external save"
    )
    stored_session = session.exec(select(SignoffAssistSession)).one()
    assert stored_session.operator_decision == "manually_completed"


def test_signoff_decision_revokes_pairing_key_and_blocks_old_preview(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={
            "decision": "manually_completed",
            "external_completion_mark": "operator confirmed external save",
        },
    )

    assert response.status_code == 200
    stored_key = session.exec(select(SignoffPairingKey)).one()
    assert stored_key.status == SignoffPairingKeyStatus.revoked
    assert stored_key.revoked_at is not None
    client.cookies.clear()
    client.headers.clear()
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 404
    candidate = session.get(ReturnSignoffCandidate, candidate_id)
    assert candidate is not None
    assert candidate.status == ReturnSignoffStatus.manually_completed


def test_signoff_decision_rejected_moves_candidate_to_review(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "needs_correction"},
    )

    assert response.status_code == 200
    assert response.json()["candidate"]["status"] == ReturnSignoffStatus.needs_review


def test_signoff_decision_rejected_is_recorded(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)
    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "rejected"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["status"] == ReturnSignoffStatus.needs_review
    assert payload["assist_session"]["operator_decision"] == "rejected"
    stored_key = session.exec(select(SignoffPairingKey)).one()
    assert stored_key.status == SignoffPairingKeyStatus.revoked
    assert stored_key.revoked_at is not None
    client.cookies.clear()
    client.headers.clear()
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 404


def test_signoff_decision_rejects_unknown_value(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "external_submitted"},
    )

    assert response.status_code == 422


def test_signoff_decision_requires_preview_and_cannot_overwrite(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)

    no_preview = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "accepted"},
    )
    assert no_preview.status_code == 409

    token = client.post(f"/api/signoff/candidates/{candidate_id}/pairing-keys").json()["token"]
    assert client.get(f"/api/signoff/assist/{token}/preview").status_code == 200
    first = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "accepted"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "manually_completed"},
    )
    assert second.status_code == 409


def test_signoff_decision_requires_supervisor(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    candidate_id = _signoff_candidate(client, session)

    operator = create_user(
        session,
        username="decision-operator",
        display_name="Decision Operator",
        password="decision-operator-pass",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    set_authenticated_session(client, token)

    response = client.post(
        f"/api/signoff/candidates/{candidate_id}/decisions",
        json={"decision": "accepted"},
    )

    assert response.status_code == 403
