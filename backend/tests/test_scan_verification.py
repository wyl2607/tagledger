from openpyxl import Workbook

from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)
from backend.app.services.material_mapping import MaterialMatch
from backend.app.services.outbound_reconciliation import register_outbound_scan


def _prepare_workbook(path) -> None:
    workbook = Workbook()
    shipping = workbook.active
    shipping.title = "ship"
    shipping.append(["出库单号", "数量", "备件编码", "备件名称"])
    shipping.append(["SO202604210135", 1, "C.P.XS.000122001", "RTK"])
    cutting = workbook.create_sheet("cut")
    cutting.append(["数量", "备件编码", "备件名称", "库位"])
    cutting.append([1, "C.P.XS.000122001", "RTK", "A-B03-011"])
    workbook.save(path)


def _login_scan_operator(client, session) -> None:
    user = create_user(
        session,
        username="scan-phone-a",
        display_name="Scan Phone A",
        password="scan-phone-pass",
        role="operator",
        outbound_last_order_no="SO202604210135",
    )
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    csrf_token = "pytest-csrf-token"
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf_token)
    client.headers.update({CSRF_HEADER: csrf_token})


def test_mismatch_part_requires_verification_record(tmp_path, monkeypatch, session) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)

    from backend.app.services import outbound_reconciliation

    class FakeSettings:
        outbound_workbook_file = path
        outbound_shipping_sheet = "ship"
        outbound_cutting_sheet = "cut"
        outbound_cutting_text_file = tmp_path / "missing-cut.txt"
        outbound_shipping_text_file = tmp_path / "missing-ship.txt"
        rollback_window_minutes = 30

    monkeypatch.setattr(outbound_reconciliation, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        outbound_reconciliation,
        "find_material_matches",
        lambda code: [
            MaterialMatch(
                ruiyun_part_number="C.P.XS.000122001",
                sku="SKU-NEED-VERIFY",
                matched_input=code,
                matched_field="sku",
            )
        ],
    )

    try:
        register_outbound_scan(
            order_no="SO202604210135",
            code="SKU-NEED-VERIFY C.P.XS.000006000",
            operator_id="phone-a",
            session=session,
            quantity=1,
            location_code="A-B03-011",
        )
    except outbound_reconciliation.OutboundVerificationRequiredError as exc:
        assert "verification_record_id is required" in str(exc)
    else:
        raise AssertionError("expected verification requirement error")


def test_mismatch_part_with_verification_record_succeeds(tmp_path, monkeypatch, session) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)

    from backend.app.services import outbound_reconciliation

    class FakeSettings:
        outbound_workbook_file = path
        outbound_shipping_sheet = "ship"
        outbound_cutting_sheet = "cut"
        outbound_cutting_text_file = tmp_path / "missing-cut.txt"
        outbound_shipping_text_file = tmp_path / "missing-ship.txt"
        rollback_window_minutes = 30

    monkeypatch.setattr(outbound_reconciliation, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        outbound_reconciliation,
        "find_material_matches",
        lambda code: [
            MaterialMatch(
                ruiyun_part_number="C.P.XS.000122001",
                sku="SKU-NEED-VERIFY",
                matched_input=code,
                matched_field="sku",
            )
        ],
    )

    result = register_outbound_scan(
        order_no="SO202604210135",
        code="SKU-NEED-VERIFY C.P.XS.000006000",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-011",
        verification_record_id=9876,
    )

    assert result["scan_saved"] is True
    assert result["requires_verification"] is True
    assert result["scan"]["verification_record_id"] == 9876


def test_scan_api_returns_422_when_verification_record_missing(
    tmp_path, monkeypatch, client, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)

    from backend.app.services import outbound_reconciliation

    class FakeSettings:
        outbound_workbook_file = path
        outbound_shipping_sheet = "ship"
        outbound_cutting_sheet = "cut"
        outbound_cutting_text_file = tmp_path / "missing-cut.txt"
        outbound_shipping_text_file = tmp_path / "missing-ship.txt"
        rollback_window_minutes = 30

    monkeypatch.setattr(outbound_reconciliation, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        outbound_reconciliation,
        "find_material_matches",
        lambda code: [
            MaterialMatch(
                ruiyun_part_number="C.P.XS.000122001",
                sku="SKU-NEED-VERIFY",
                matched_input=code,
                matched_field="sku",
            )
        ],
    )

    _login_scan_operator(client, session)

    response = client.post(
        "/api/outbound/scan",
        json={
            "order_no": "SO202604210135",
            "code": "SKU-NEED-VERIFY C.P.XS.000006000",
            "operator_id": "phone-a",
            "quantity": 1,
            "location_code": "A-B03-011",
        },
    )
    assert response.status_code == 422
    assert "verification_record_id is required" in response.text


def test_scan_api_accepts_mismatch_with_verification_record(
    tmp_path, monkeypatch, client, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)

    from backend.app.services import outbound_reconciliation

    class FakeSettings:
        outbound_workbook_file = path
        outbound_shipping_sheet = "ship"
        outbound_cutting_sheet = "cut"
        outbound_cutting_text_file = tmp_path / "missing-cut.txt"
        outbound_shipping_text_file = tmp_path / "missing-ship.txt"
        rollback_window_minutes = 30

    monkeypatch.setattr(outbound_reconciliation, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        outbound_reconciliation,
        "find_material_matches",
        lambda code: [
            MaterialMatch(
                ruiyun_part_number="C.P.XS.000122001",
                sku="SKU-NEED-VERIFY",
                matched_input=code,
                matched_field="sku",
            )
        ],
    )

    _login_scan_operator(client, session)

    response = client.post(
        "/api/outbound/scan",
        json={
            "order_no": "SO202604210135",
            "code": "SKU-NEED-VERIFY C.P.XS.000006000",
            "operator_id": "phone-a",
            "quantity": 1,
            "location_code": "A-B03-011",
            "verification_record_id": 10086,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_saved"] is True
    assert payload["scan"]["verification_record_id"] == 10086
