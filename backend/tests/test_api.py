import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.models import Category, Record, RecordStatus
from backend.app.services.auth_service import CSRF_COOKIE, CSRF_HEADER, create_session, create_user
from backend.app.services.material_mapping import MaterialMatch

STATIC_UI_PAGES = [
    Path("backend/app/static/home.html"),
    Path("backend/app/static/login.html"),
    Path("backend/app/static/setup.html"),
    Path("backend/app/static/admin.html"),
    Path("backend/app/static/mobile.html"),
    Path("backend/app/static/outbound.html"),
    Path("backend/app/static/transfers.html"),
    Path("backend/app/static/signoff.html"),
]


def _static_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_health(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_url_can_be_overridden_for_isolated_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from backend.app import config as config_module

    config_module.get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'isolated.db'}")
    try:
        settings = config_module.get_settings()
    finally:
        config_module.get_settings.cache_clear()

    assert settings.database_path == tmp_path / "isolated.db"


def test_database_url_normalization_supports_alembic() -> None:
    from backend.app.config import Settings, normalize_database_url

    assert (
        normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert Settings(database_url="sqlite:///data/app.db").resolved_database_url.endswith(
        "/data/app.db"
    )


def test_runtime_status_exposes_mobile_test_switches(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ocr_provider"] in {"mock", "tesseract"}
    assert isinstance(payload["enable_barcode"], bool)
    assert isinstance(payload["enable_saas_submit"], bool)
    assert isinstance(payload["dry_run"], bool)
    assert payload["mobile_url"].endswith("/mobile")
    assert payload["history_url"].endswith("/history")


def test_startup_restore_skips_submission_queue_when_saas_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app import main as main_module
    from backend.app.config import Settings

    calls: list[bool] = []

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: Settings(enable_saas_submit=False),
    )
    monkeypatch.setattr(
        main_module,
        "enqueue_pending_confirmed",
        lambda: calls.append(True) or 1,
    )

    assert main_module.restore_pending_submissions() == 0
    assert calls == []


def test_startup_restore_enqueues_submission_queue_when_saas_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app import main as main_module
    from backend.app.config import Settings

    calls: list[bool] = []

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: Settings(enable_saas_submit=True),
    )
    monkeypatch.setattr(
        main_module,
        "enqueue_pending_confirmed",
        lambda: calls.append(True) or 3,
    )

    assert main_module.restore_pending_submissions() == 3
    assert calls == [True]


def test_static_ui_asset_paths_are_served(authenticated_client: TestClient) -> None:
    for path in (
        "/static/ui.css",
        "/static/i18n.js",
        "/static/auth-ui.js",
        "/static/i18n/en.json",
        "/static/i18n/de.json",
        "/static/i18n/zh.json",
    ):
        response = authenticated_client.get(path)
        assert response.status_code == 200, path


def test_status_badge_colors_are_declared(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/static/ui.css")

    assert response.status_code == 200
    css = response.text
    assert ".status-confirmed" in css
    assert "#dcfce7" in css
    assert ".status-submitted" in css
    assert ".status-submission_failed" in css
    assert ".status-duplicate" in css
    assert ".status-needs_review" in css


def test_capture_serves_mac_demo_page(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/capture")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TagLedger" in response.text
    assert 'data-i18n="demo.title"' in response.text
    assert '<section class="guide"' in response.text
    assert "/upload" in response.text
    assert "/upload/batch" in response.text
    assert "/jobs" in response.text
    assert "/confirm/" in response.text
    assert "/export.csv?status=confirmed" in response.text
    assert 'data-i18n="duplicate.action.discardNew"' in response.text
    assert 'data-i18n="material.title"' in response.text
    assert "renderMaterialMatches" in response.text


def test_history_page_serves_history_view(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/history")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "历史记录 · TagLedger" in response.text
    assert 'data-i18n="history.title"' in response.text
    assert "/records/" in response.text
    assert "/export.csv" in response.text
    assert "imageFallbackDataUri" in response.text


def test_dashboard_page_serves_html(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TagLedger 统计面板" in response.text
    assert "/api/metrics/all" in response.text
    assert 'data-i18n="dashboard.title"' in response.text
    assert 'id="inventoryTotalQty"' in response.text
    assert 'id="zeroStockLocations"' in response.text
    assert 'id="recentInboundQty"' in response.text
    assert 'id="activeOutboundQty"' in response.text


def test_outbound_page_serves_html(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/outbound")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "出库核对" in response.text
    assert "/api/outbound/summary" in response.text
    assert "/api/outbound/query" in response.text
    assert "data-order-choice" in response.text
    assert "belongs_to_selected" in response.text
    assert "displayValue(row.quantity)" in response.text
    assert "displayValue(row.cutting_qty)" in response.text
    assert "displayValue(row.shipping_qty)" in response.text
    assert "displayValue(row.difference)" in response.text
    assert "row.quantity || '-'" not in response.text
    assert "String(value || '')" not in response.text
    assert "/login?next=" in response.text
    assert "/static/i18n.js" in response.text
    assert "outbound.page.title" in response.text


def test_auth_pages_are_linked_from_static_routes(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/workbench")

    assert response.status_code == 200
    assert "/api/workbench" in response.text
    assert "/static/i18n.js" in response.text
    assert "workbench.modules.title" in response.text


def test_signoff_page_serves_management_console(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/signoff")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'data-i18n="signoff.title"' in response.text
    assert "/api/signoff/candidates" in response.text
    assert "can_manage_signoff" in response.text


def test_static_role_ui_contracts_are_explicit() -> None:
    workbench = _static_text("backend/app/static/home.html")
    mobile = _static_text("backend/app/static/mobile.html")
    admin = _static_text("backend/app/static/admin.html")
    transfers = _static_text("backend/app/static/transfers.html")
    signoff = _static_text("backend/app/static/signoff.html")

    assert "renderModules(payload.modules || [])" in workbench
    assert "payload.global_stats" in workbench
    assert 'href="/admin"' not in mobile
    assert 'href="/transfers"' not in mobile
    assert 'href="/dashboard"' not in mobile
    assert 'id="adminContent" hidden' in admin
    assert 'id="accessDenied" hidden' in admin
    assert 'id="createUserForm"' in admin
    assert 'id="assignedOrder"' in admin
    assert "outbound_last_order_no" in admin
    assert "can_manage_users" in admin
    assert 'id="createTransferCard" hidden' in transfers
    assert "can_manage_transfers" in transfers
    assert "can_manage_signoff" in signoff
    assert "/api/signoff/candidates" in signoff
    assert "copyPreview" in signoff
    assert "'Content-Type': 'application/json'" in signoff
    assert "/api/signoff/pairing-keys/${pairingKeyId}/revoke" in signoff


def test_static_i18n_keys_exist_for_three_languages() -> None:
    locale_payloads = {
        locale: json.loads(
            Path(f"backend/app/static/i18n/{locale}.json").read_text(encoding="utf-8")
        )
        for locale in ("zh", "en", "de")
    }
    key_pattern = re.compile(
        r"""data-i18n(?:-placeholder)?=["']([^"']+)["']|tr\(["']([^"']+)["']"""
    )
    keys: set[str] = set()
    for path in STATIC_UI_PAGES:
        text = path.read_text(encoding="utf-8")
        for match in key_pattern.finditer(text):
            keys.add(next(group for group in match.groups() if group))

    missing = {
        locale: sorted(key for key in keys if key not in payload)
        for locale, payload in locale_payloads.items()
    }
    assert missing == {"zh": [], "en": [], "de": []}


def test_write_endpoints_require_login_even_with_valid_csrf(
    client: TestClient,
    session: Session,
) -> None:
    csrf_token = "anonymous-csrf-token"
    client.cookies.set(CSRF_COOKIE, csrf_token)
    client.headers.update({CSRF_HEADER: csrf_token})
    record = Record(
        image_path="pending.jpg",
        category=Category.A,
        status=RecordStatus.ocr_done,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    upload = client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("anon.jpg", b"fake image", "image/jpeg")},
    )
    confirm = client.post(
        f"/confirm/{record.id}",
        json={"category": "A", "duplicate_action": "overwrite"},
    )
    retry_one = client.post(f"/jobs/retry/{record.id}")
    retry_all = client.post("/jobs/retry")

    assert upload.status_code == 401
    assert confirm.status_code == 401
    assert retry_one.status_code == 401
    assert retry_all.status_code == 401


def test_outbound_query_accepts_multiple_selected_orders(
    authenticated_client: TestClient, session: Session, monkeypatch
) -> None:
    from backend.app.routes import outbound

    captured = {}

    def fake_query(code, selected_orders=None, allowed_orders=None):
        captured["code"] = code
        captured["selected_orders"] = selected_orders
        captured["allowed_orders"] = allowed_orders
        return {"query": code, "selected_order_numbers": selected_orders or []}

    monkeypatch.setattr(outbound, "query_outbound", fake_query)
    manager = create_user(
        session,
        username="query-manager",
        display_name="Query Manager",
        password="query-manager-pass",
        role="manager",
    )
    token, _ = create_session(session, manager, ip_address="testclient", user_agent="pytest")
    authenticated_client.cookies.set("mlocr_session", token)

    response = authenticated_client.get(
        "/api/outbound/query",
        params=[("code", "C.P.XS.000142004"), ("order_no", "SO1"), ("order_no", "SO2")],
    )

    assert response.status_code == 200
    assert captured == {
        "code": "C.P.XS.000142004",
        "selected_orders": ["SO1", "SO2"],
        "allowed_orders": None,
    }


def test_mobile_page_serves_phone_intake_view(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/mobile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Mobile Capture" in response.text
    assert 'data-i18n="nav.mobile"' in response.text
    assert 'capture="environment"' in response.text
    assert "/upload" in response.text
    assert "/confirm/" in response.text
    assert 'data-i18n="mobile.capture.camera"' in response.text
    assert "autoUpload: true" in response.text
    assert "/runtime/status" in response.text
    assert 'data-i18n="material.title"' in response.text


def test_static_ui_assets_are_served(authenticated_client: TestClient) -> None:
    for path, expected in [
        ("/static/ui.css", "#ff6b35"),
        ("/static/i18n.js", "window.I18n"),
        ("/static/auth-ui.js", "AuthUI"),
        ("/static/i18n/en.json", "TagLedger"),
        ("/static/i18n/de.json", "Feldaufnahme"),
        ("/static/i18n/zh.json", "现场录入"),
    ]:
        response = authenticated_client.get(path)
        assert response.status_code == 200
        assert expected in response.text


def test_demo_api_full_flow(authenticated_client: TestClient) -> None:
    upload = authenticated_client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("demo.jpg", b"fake image", "image/jpeg")},
    )
    assert upload.status_code == 200
    record_id = upload.json()["job_id"]

    job = authenticated_client.get(f"/jobs/{record_id}")
    assert job.status_code == 200
    job_payload = job.json()

    confirm = authenticated_client.post(
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

    exported = authenticated_client.get("/export.csv", params={"status": "confirmed"})
    assert exported.status_code == 200
    assert job_payload["vin_or_bin"] in exported.text


def test_upload_runs_mock_ocr_and_job_can_be_read(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("label.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"

    job = authenticated_client.get(f"/jobs/{payload['job_id']}")
    assert job.status_code == 200
    job_payload = job.json()
    assert job_payload["status"] == "ocr_done"
    assert job_payload["model"].startswith("MOCK-")
    assert job_payload["vin_or_bin"].startswith("VIN-")
    assert job_payload["serial_number"].startswith("SN-")
    assert job_payload["last_error"] is None
    assert "created_at" in job_payload
    assert "updated_at" in job_payload


def test_job_returns_material_mapping_matches(
    authenticated_client: TestClient, session: Session, monkeypatch
) -> None:
    from backend.app.routes import jobs

    record = Record(
        image_path="label.jpg",
        category=Category.A,
        raw_ocr_text="SKU: MTL24LUM1US02",
        status=RecordStatus.ocr_done,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    monkeypatch.setattr(
        jobs,
        "find_material_matches",
        lambda text: [
            MaterialMatch(
                ruiyun_part_number="C.G.LM.000011000",
                sku="MTL24LUM1US02",
                matched_input="MTL24LUM1US02",
                matched_field="sku",
            )
        ],
    )

    response = authenticated_client.get(f"/jobs/{record.id}")

    assert response.status_code == 200
    assert response.json()["material_matches"] == [
        {
            "ruiyun_part_number": "C.G.LM.000011000",
            "sku": "MTL24LUM1US02",
            "matched_input": "MTL24LUM1US02",
            "matched_field": "sku",
        }
    ]


def test_upload_material_mapping_checks_duplicates_after_autofill(
    authenticated_client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.workers import ocr_worker

    existing = Record(
        image_path="existing.jpg",
        category=Category.A,
        vin_or_bin="C.G.LM.000011000",
        serial_number="MTL24LUM1US02",
        status=RecordStatus.confirmed,
    )
    session.add(existing)
    session.commit()

    monkeypatch.setattr(
        ocr_worker,
        "find_material_matches",
        lambda text: [
            MaterialMatch(
                ruiyun_part_number="C.G.LM.000011000",
                sku="MTL24LUM1US02",
                matched_input="MTL24LUM1US02",
                matched_field="sku",
            )
        ],
    )

    response = authenticated_client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("mapped.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    record = session.get(Record, response.json()["job_id"])
    assert record is not None
    assert record.status == RecordStatus.duplicate
    assert record.vin_or_bin == "C.G.LM.000011000"
    assert record.serial_number == "MTL24LUM1US02"


def test_upload_saves_operator_id_and_jobs_filter_by_operator(
    authenticated_client: TestClient,
) -> None:
    first = authenticated_client.post(
        "/upload",
        data={"category": "A", "operator_id": "phone-alpha"},
        files={"file": ("alpha.jpg", b"fake image", "image/jpeg")},
    )
    second = authenticated_client.post(
        "/upload",
        data={"category": "A", "operator_id": "phone-beta"},
        files={"file": ("beta.jpg", b"fake image", "image/jpeg")},
    )

    assert first.status_code == 200
    assert second.status_code == 200

    response = authenticated_client.get("/jobs", params={"operator_id": "phone-alpha", "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert [row["operator_id"] for row in payload] == ["phone-alpha"]
    assert payload[0]["id"] == first.json()["job_id"]


def test_jobs_filter_before_pagination(authenticated_client: TestClient) -> None:
    first = authenticated_client.post(
        "/upload",
        data={"category": "A", "operator_id": "phone-alpha"},
        files={"file": ("alpha.jpg", b"fake image", "image/jpeg")},
    )
    for index in range(3):
        response = authenticated_client.post(
            "/upload",
            data={"category": "A", "operator_id": "phone-beta"},
            files={"file": (f"beta-{index}.jpg", b"fake image", "image/jpeg")},
        )
        assert response.status_code == 200

    response = authenticated_client.get("/jobs", params={"operator_id": "phone-alpha", "limit": 1})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [first.json()["job_id"]]


def test_upload_mock_flow_is_unchanged_when_barcode_disabled(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.config import Settings
    from backend.app.ocr import factory

    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: Settings(ocr_provider="mock", enable_barcode=False),
    )

    response = authenticated_client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("mock-only.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["barcodes"] == []

    job = authenticated_client.get(f"/jobs/{payload['job_id']}")
    assert job.status_code == 200
    job_payload = job.json()
    assert job_payload["status"] == "ocr_done"
    assert job_payload["model"].startswith("MOCK-")
    assert job_payload["vin_or_bin"].startswith("VIN-")
    assert job_payload["serial_number"].startswith("SN-")
    assert job_payload["barcodes"] == []
    assert job_payload["last_error"] is None


def test_upload_rejects_unsupported_file_extension(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/upload",
        data={"category": "A"},
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "unsupported image extension" in response.json()["detail"]


def test_batch_upload_returns_multiple_jobs(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
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
        record = authenticated_client.get(f"/jobs/{job['job_id']}")
        assert record.status_code == 200
        assert record.json()["status"] == "ocr_done"


def test_upload_normalizes_blank_duplicate_fields(
    authenticated_client: TestClient, session: Session
) -> None:
    response = authenticated_client.post(
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
    authenticated_client: TestClient,
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

    response = authenticated_client.post(
        "/upload",
        data={"category": "A", "vin_or_bin": "vin100"},
        files={"file": ("dup.jpg", b"fake image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "duplicate"
    assert payload["duplicates"][0]["id"] == existing.id


def test_confirm_abandon_keeps_existing_record(
    authenticated_client: TestClient, session: Session
) -> None:
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

    response = authenticated_client.post(
        f"/confirm/{current.id}",
        json={"vin_or_bin": "VIN200", "serial_number": "SN200", "duplicate_action": "abandon"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"
    session.refresh(existing)
    assert existing.status == RecordStatus.confirmed
    assert existing.vin_or_bin == "VIN200"


def test_confirm_overwrite_replaces_existing_record(
    authenticated_client: TestClient, session: Session
) -> None:
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

    response = authenticated_client.post(
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
    authenticated_client: TestClient,
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
        response = authenticated_client.post(
            f"/confirm/{current.id}",
            json={"vin_or_bin": "VIN-LOCAL", "duplicate_action": "overwrite"},
        )
    finally:
        app.dependency_overrides[get_submit_runner] = lambda: lambda record_id: None

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert calls == []


def test_confirm_enqueues_submit_when_saas_enabled(
    authenticated_client: TestClient,
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
        response = authenticated_client.post(
            f"/confirm/{current.id}",
            json={"vin_or_bin": "VIN-SUBMIT", "duplicate_action": "overwrite"},
        )
    finally:
        app.dependency_overrides[get_submit_runner] = lambda: lambda record_id: None

    assert response.status_code == 200
    assert calls == [current.id]


def test_export_csv_contains_records(authenticated_client: TestClient, session: Session) -> None:
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

    response = authenticated_client.get("/export.csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "vin_or_bin" in response.text
    assert "VIN400" in response.text


def test_get_record_image_returns_file(
    authenticated_client: TestClient, session: Session, tmp_path
) -> None:
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

    response = authenticated_client.get(f"/records/{record.id}/image")

    assert response.status_code == 200
    assert response.content == b"fake jpeg bytes"


def test_list_jobs_supports_status_limit_and_offset(
    authenticated_client: TestClient, session: Session
) -> None:
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

    response = authenticated_client.get(
        "/jobs", params={"status": "ocr_done", "limit": 1, "offset": 0}
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == second.id
    assert payload[0]["status"] == "ocr_done"
    assert "raw_ocr_text" not in payload[0]


def test_list_jobs_rejects_invalid_status(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/jobs", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_export_csv_supports_status_filter(
    authenticated_client: TestClient, session: Session
) -> None:
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

    response = authenticated_client.get("/export.csv", params={"status": "confirmed"})

    assert response.status_code == 200
    assert "VIN-CONFIRMED" in response.text
    assert "VIN-DUP-EXPORT" not in response.text


def test_export_csv_supports_history_filters(
    authenticated_client: TestClient, session: Session
) -> None:
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

    response = authenticated_client.get(
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


def test_export_csv_rejects_invalid_status(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/export.csv", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_missing_job_returns_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/jobs/999999")

    assert response.status_code == 404


def test_mobile_page_serves_mobile_optimized_view(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/mobile")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Mobile Capture" in response.text
    assert "capture=" in response.text
    assert "mobile.action.confirm" in response.text
    assert "mobile.action.next" in response.text
    assert "compressImage" in response.text
    assert "lastAutoUploadedSignature" in response.text
    assert "mobile.done.duplicate" in response.text
    assert "mobile.step.capture" in response.text
    assert "mobile.capture.locator" in response.text
    assert "mobile.mine.uploaded" in response.text
    assert "operator_id" in response.text
