import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.models import Category, Record, RecordStatus


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runtime_status_exposes_mobile_test_switches(client: TestClient) -> None:
    response = client.get("/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ocr_provider"] in {"mock", "tesseract"}
    assert isinstance(payload["enable_barcode"], bool)
    assert isinstance(payload["enable_saas_submit"], bool)
    assert isinstance(payload["dry_run"], bool)


def test_demo_home_serves_mac_demo_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "机器标签拍照上传" in response.text
    assert "/upload" in response.text
    assert "/jobs" in response.text
    assert "/confirm/" in response.text
    assert "/export.csv?status=confirmed" in response.text
    assert "重复时放弃新记录" in response.text


def test_history_page_serves_history_view(client: TestClient) -> None:
    response = client.get("/history")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "历史记录" in response.text
    assert "/records/" in response.text
    assert "/export.csv" in response.text


def test_mobile_page_serves_phone_intake_view(client: TestClient) -> None:
    response = client.get("/mobile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "手机录入" in response.text
    assert 'capture="environment"' in response.text
    assert "/upload" in response.text
    assert "/confirm/" in response.text
    assert "拍照识别" in response.text
    assert "autoUpload: true" in response.text
    assert "/runtime/status" in response.text


def test_demo_api_full_flow(client: TestClient) -> None:
    upload = client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("demo.jpg", b"fake image", "image/jpeg")},
    )
    assert upload.status_code == 200
    record_id = upload.json()["job_id"]

    job = client.get(f"/jobs/{record_id}")
    assert job.status_code == 200
    job_payload = job.json()

    confirm = client.post(
        f"/confirm/{record_id}",
        json={
            "category": job_payload["category"],
            "model": job_payload["model"],
            "vin_or_bin": job_payload["vin_or_bin"],
            "serial_number": job_payload["serial_number"],
            "duplicate_action": "overwrite",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "confirmed"

    exported = client.get("/export.csv", params={"status": "confirmed"})
    assert exported.status_code == 200
    assert job_payload["vin_or_bin"] in exported.text


def test_upload_runs_mock_ocr_and_job_can_be_read(client: TestClient) -> None:
    response = client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("label.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"

    job = client.get(f"/jobs/{payload['job_id']}")
    assert job.status_code == 200
    job_payload = job.json()
    assert job_payload["status"] == "ocr_done"
    assert job_payload["model"].startswith("MOCK-")
    assert job_payload["vin_or_bin"].startswith("VIN-")
    assert job_payload["serial_number"].startswith("SN-")
    assert job_payload["last_error"] is None
    assert "created_at" in job_payload
    assert "updated_at" in job_payload


def test_upload_mock_flow_is_unchanged_when_barcode_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.config import Settings
    from backend.app.ocr import factory

    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: Settings(ocr_provider="mock", enable_barcode=False),
    )

    response = client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("mock-only.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["barcodes"] == []

    job = client.get(f"/jobs/{payload['job_id']}")
    assert job.status_code == 200
    job_payload = job.json()
    assert job_payload["status"] == "ocr_done"
    assert job_payload["model"].startswith("MOCK-")
    assert job_payload["vin_or_bin"].startswith("VIN-")
    assert job_payload["serial_number"].startswith("SN-")
    assert job_payload["barcodes"] == []
    assert job_payload["last_error"] is None


def test_upload_rejects_unsupported_file_extension(client: TestClient) -> None:
    response = client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "unsupported image extension" in response.json()["detail"]


def test_batch_upload_returns_multiple_jobs(client: TestClient) -> None:
    response = client.post(
        "/upload/batch",
        data={"category": "A"},
        files=[
            ("files", ("batch-one.jpg", b"fake image 1", "image/jpeg")),
            ("files", ("batch-two.png", b"fake image 2", "image/png")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert [job["filename"] for job in payload["jobs"]] == ["batch-one.jpg", "batch-two.png"]
    assert [job["status"] for job in payload["jobs"]] == ["uploaded", "uploaded"]
    assert all(job["job_id"] for job in payload["jobs"])

    for job in payload["jobs"]:
        record = client.get(f"/jobs/{job['job_id']}")
        assert record.status_code == 200
        assert record.json()["status"] == "ocr_done"


def test_upload_normalizes_blank_duplicate_fields(client: TestClient, session: Session) -> None:
    response = client.post(
        "/upload",
        data={"category": "B", "vin_or_bin": "   ", "serial_number": ""},
        files={"file": ("blank.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    record = session.get(Record, response.json()["job_id"])
    assert record is not None
    assert record.vin_or_bin.startswith("VIN-")
    assert record.serial_number.startswith("SN-")


def test_upload_duplicate_hint_returns_duplicate_without_ocr(
    client: TestClient,
    session: Session,
) -> None:
    existing = Record(
        image_path="existing.jpg",
        category=Category.A,
        vin_or_bin="VIN100",
        serial_number="SN100",
        status=RecordStatus.confirmed,
    )
    session.add(existing)
    session.commit()

    response = client.post(
        "/upload",
        data={"category": "A", "vin_or_bin": "vin100"},
        files={"file": ("dup.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "duplicate"
    assert payload["duplicates"][0]["id"] == existing.id


def test_confirm_abandon_keeps_existing_record(client: TestClient, session: Session) -> None:
    existing = Record(
        image_path="existing.jpg",
        category=Category.A,
        vin_or_bin="VIN200",
        serial_number="SN200",
        status=RecordStatus.confirmed,
    )
    current = Record(
        image_path="current.jpg",
        category=Category.B,
        status=RecordStatus.ocr_done,
    )
    session.add(existing)
    session.add(current)
    session.commit()
    session.refresh(current)

    response = client.post(
        f"/confirm/{current.id}",
        json={"vin_or_bin": "VIN200", "serial_number": "SN200", "duplicate_action": "abandon"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"
    session.refresh(existing)
    assert existing.status == RecordStatus.confirmed
    assert existing.vin_or_bin == "VIN200"


def test_confirm_overwrite_replaces_existing_record(client: TestClient, session: Session) -> None:
    existing = Record(
        image_path="existing.jpg",
        category=Category.A,
        vin_or_bin="VIN300",
        serial_number="SN300",
        status=RecordStatus.confirmed,
    )
    current = Record(
        image_path="current.jpg",
        category=Category.B,
        status=RecordStatus.ocr_done,
    )
    session.add(existing)
    session.add(current)
    session.commit()
    session.refresh(existing)
    session.refresh(current)

    response = client.post(
        f"/confirm/{current.id}",
        json={
            "category": "C",
            "model": "Model 300",
            "vin_or_bin": "VIN300",
            "serial_number": "SN300",
            "duplicate_action": "overwrite",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    session.refresh(existing)
    session.refresh(current)
    assert existing.status == RecordStatus.duplicate
    assert existing.vin_or_bin is None
    assert existing.serial_number is None
    assert current.status == RecordStatus.confirmed
    assert current.category == Category.C
    assert current.model == "MODEL 300"


def test_confirm_does_not_enqueue_submit_when_saas_disabled(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.config import Settings
    from backend.app.main import app
    from backend.app.routes import confirm as confirm_route
    from backend.app.routes.confirm import get_submit_runner

    calls: list[int] = []
    current = Record(
        image_path="local-only.jpg",
        category=Category.A,
        status=RecordStatus.ocr_done,
    )
    session.add(current)
    session.commit()
    session.refresh(current)

    monkeypatch.setattr(
        confirm_route,
        "get_settings",
        lambda: Settings(enable_saas_submit=False),
    )
    app.dependency_overrides[get_submit_runner] = lambda: calls.append
    try:
        response = client.post(
            f"/confirm/{current.id}",
            json={"vin_or_bin": "VIN-LOCAL", "duplicate_action": "overwrite"},
        )
    finally:
        app.dependency_overrides[get_submit_runner] = lambda: lambda record_id: None

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert calls == []


def test_confirm_enqueues_submit_when_saas_enabled(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.config import Settings
    from backend.app.main import app
    from backend.app.routes import confirm as confirm_route
    from backend.app.routes.confirm import get_submit_runner

    calls: list[int] = []
    current = Record(
        image_path="submit-enabled.jpg",
        category=Category.A,
        status=RecordStatus.ocr_done,
    )
    session.add(current)
    session.commit()
    session.refresh(current)

    monkeypatch.setattr(
        confirm_route,
        "get_settings",
        lambda: Settings(enable_saas_submit=True),
    )
    app.dependency_overrides[get_submit_runner] = lambda: calls.append
    try:
        response = client.post(
            f"/confirm/{current.id}",
            json={"vin_or_bin": "VIN-SUBMIT", "duplicate_action": "overwrite"},
        )
    finally:
        app.dependency_overrides[get_submit_runner] = lambda: lambda record_id: None

    assert response.status_code == 200
    assert calls == [current.id]


def test_export_csv_contains_records(client: TestClient, session: Session) -> None:
    session.add(
        Record(
            image_path="export.jpg",
            category=Category.A,
            model="EXPORT-MODEL",
            vin_or_bin="VIN400",
            serial_number="SN400",
            status=RecordStatus.confirmed,
        )
    )
    session.commit()

    response = client.get("/export.csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "vin_or_bin" in response.text
    assert "VIN400" in response.text


def test_get_record_image_returns_file(client: TestClient, session: Session, tmp_path) -> None:
    image_path = tmp_path / "history-image.jpg"
    image_path.write_bytes(b"fake jpeg bytes")
    record = Record(
        image_path=str(image_path),
        category=Category.A,
        status=RecordStatus.confirmed,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    response = client.get(f"/records/{record.id}/image")

    assert response.status_code == 200
    assert response.content == b"fake jpeg bytes"


def test_list_jobs_supports_status_limit_and_offset(client: TestClient, session: Session) -> None:
    first = Record(
        image_path="first.jpg",
        category=Category.A,
        vin_or_bin="VIN-LIST-1",
        serial_number="SN-LIST-1",
        status=RecordStatus.confirmed,
    )
    second = Record(
        image_path="second.jpg",
        category=Category.B,
        vin_or_bin="VIN-LIST-2",
        serial_number="SN-LIST-2",
        status=RecordStatus.ocr_done,
    )
    session.add(first)
    session.add(second)
    session.commit()
    session.refresh(first)
    session.refresh(second)

    response = client.get("/jobs", params={"status": "ocr_done", "limit": 1, "offset": 0})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == second.id
    assert payload[0]["status"] == "ocr_done"
    assert "raw_ocr_text" not in payload[0]


def test_list_jobs_rejects_invalid_status(client: TestClient) -> None:
    response = client.get("/jobs", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_export_csv_supports_status_filter(client: TestClient, session: Session) -> None:
    session.add(
        Record(
            image_path="confirmed.jpg",
            category=Category.A,
            vin_or_bin="VIN-CONFIRMED",
            serial_number="SN-CONFIRMED",
            status=RecordStatus.confirmed,
        )
    )
    session.add(
        Record(
            image_path="duplicate.jpg",
            category=Category.B,
            vin_or_bin="VIN-DUP-EXPORT",
            serial_number="SN-DUP-EXPORT",
            status=RecordStatus.duplicate,
        )
    )
    session.commit()

    response = client.get("/export.csv", params={"status": "confirmed"})

    assert response.status_code == 200
    assert "VIN-CONFIRMED" in response.text
    assert "VIN-DUP-EXPORT" not in response.text


def test_export_csv_supports_history_filters(client: TestClient, session: Session) -> None:
    session.add(
        Record(
            image_path="history-confirmed.jpg",
            category=Category.A,
            model="HISTORY-MODEL",
            vin_or_bin="VIN-HISTORY",
            serial_number="SN-HISTORY",
            status=RecordStatus.confirmed,
        )
    )
    session.add(
        Record(
            image_path="history-duplicate.jpg",
            category=Category.B,
            model="OTHER-MODEL",
            vin_or_bin="VIN-OTHER",
            serial_number="SN-OTHER",
            status=RecordStatus.duplicate,
        )
    )
    session.commit()

    response = client.get(
        "/export.csv",
        params=[
            ("status", "confirmed"),
            ("status", "duplicate"),
            ("keyword", "history"),
        ],
    )

    assert response.status_code == 200
    assert "VIN-HISTORY" in response.text
    assert "VIN-OTHER" not in response.text


def test_export_csv_rejects_invalid_status(client: TestClient) -> None:
    response = client.get("/export.csv", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_missing_job_returns_404(client: TestClient) -> None:
    response = client.get("/jobs/999999")

    assert response.status_code == 404


def test_mobile_page_serves_mobile_optimized_view(client: TestClient) -> None:
    response = client.get("/mobile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "手机录入" in response.text
    assert "capture=" in response.text
    assert "确认入库" in response.text
    assert "继续拍下一台" in response.text
    assert "compressImage" in response.text
    assert "lastAutoUploadedSignature" in response.text
    assert "已标记重复" in response.text
    assert "拍标签，确认入库" in response.text
