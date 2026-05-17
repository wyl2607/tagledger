import pytest
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from backend.app.models import InventoryLocation, InventoryMovement, OutboundScan
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)
from backend.app.services.material_mapping import MaterialMatch
from backend.app.services.outbound_reconciliation import register_outbound_scan


def _prepare_workbook(
    path,
    *,
    quantity: int = 1,
    location_code: str = "A-B03-011",
    extra_location_code: str | None = None,
) -> None:
    workbook = Workbook()
    shipping = workbook.active
    shipping.title = "ship"
    shipping.append(["出库单号", "数量", "备件编码", "备件名称"])
    shipping.append(["SO202604210135", quantity, "C.P.XS.000122001", "RTK"])
    cutting = workbook.create_sheet("cut")
    cutting.append(["数量", "备件编码", "备件名称", "库位", "备用库位"])
    row = [quantity, "C.P.XS.000122001", "RTK", location_code]
    if extra_location_code is not None:
        row.append(extra_location_code)
    cutting.append(row)
    workbook.save(path)


def _patch_outbound_settings(monkeypatch, path, tmp_path) -> None:
    from backend.app.services import outbound_reconciliation

    class FakeSettings:
        outbound_workbook_file = path
        outbound_shipping_sheet = "ship"
        outbound_cutting_sheet = "cut"
        outbound_cutting_text_file = tmp_path / "missing-cut.txt"
        outbound_shipping_text_file = tmp_path / "missing-ship.txt"
        rollback_window_minutes = 30

    monkeypatch.setattr(outbound_reconciliation, "get_settings", lambda: FakeSettings())


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

    _patch_outbound_settings(monkeypatch, path, tmp_path)
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

    _patch_outbound_settings(monkeypatch, path, tmp_path)
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


def test_successful_scan_decrements_selected_location_inventory(
    tmp_path, monkeypatch, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path, quantity=2)
    _patch_outbound_settings(monkeypatch, path, tmp_path)
    session.add(
        InventoryLocation(
            part_key="CPXS000122001",
            location_code="A-B03-011",
            quantity=2,
            status="active",
            zero_stock=False,
        )
    )
    session.commit()

    result = register_outbound_scan(
        order_no="SO202604210135",
        code="C.P.XS.000122001",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-011",
        record_id=101,
    )

    assert result["scan_saved"] is True
    assert result["inventory_location"]["quantity_on_hand"] == 1
    assert result["inventory_movement"]["movement_type"] == "outbound"
    assert result["inventory_movement"]["quantity_delta"] == -1
    assert result["inventory_movement"]["before_qty"] == 2
    assert result["inventory_movement"]["after_qty"] == 1
    assert result["inventory_movement"]["scan_id"] == result["scan_id"]
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122001")
    ).one()
    assert location.quantity == 1
    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122001")
    ).all()
    assert len(movements) == 1


def test_repeated_record_scan_does_not_decrement_inventory_twice(
    tmp_path, monkeypatch, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path, quantity=2)
    _patch_outbound_settings(monkeypatch, path, tmp_path)
    session.add(
        InventoryLocation(
            part_key="CPXS000122001",
            location_code="A-B03-011",
            quantity=2,
            status="active",
            zero_stock=False,
        )
    )
    session.commit()

    first = register_outbound_scan(
        order_no="SO202604210135",
        code="C.P.XS.000122001",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-011",
        record_id=202,
    )
    second = register_outbound_scan(
        order_no="SO202604210135",
        code="C.P.XS.000122001",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-011",
        record_id=202,
    )

    assert first["scan_saved"] is True
    assert second["scan_saved"] is False
    assert second["already_recorded"] is True
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122001")
    ).one()
    assert location.quantity == 1
    assert (
        len(
            session.exec(
                select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122001")
            ).all()
        )
        == 1
    )


def test_record_id_unique_index_prevents_second_location_double_decrement(
    tmp_path, monkeypatch, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path, quantity=2, extra_location_code="A-B03-012")
    _patch_outbound_settings(monkeypatch, path, tmp_path)
    session.add_all(
        [
            InventoryLocation(
                part_key="CPXS000122001",
                location_code="A-B03-011",
                quantity=2,
                status="active",
                zero_stock=False,
            ),
            InventoryLocation(
                part_key="CPXS000122001",
                location_code="A-B03-012",
                quantity=2,
                status="active",
                zero_stock=False,
            ),
        ]
    )
    session.commit()

    first = register_outbound_scan(
        order_no="SO202604210135",
        code="C.P.XS.000122001",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-011",
        record_id=404,
    )
    second = register_outbound_scan(
        order_no="SO202604210135",
        code="C.P.XS.000122001",
        operator_id="phone-a",
        session=session,
        quantity=1,
        location_code="A-B03-012",
        record_id=404,
    )

    assert first["scan_saved"] is True
    assert second["scan_saved"] is False
    assert second["already_recorded"] is True
    rows = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122001")
    ).all()
    by_location = {row.location_code: row.quantity for row in rows}
    assert by_location == {"A-B03-011": 1, "A-B03-012": 2}
    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122001")
    ).all()
    assert [(movement.location_code, movement.quantity_delta) for movement in movements] == [
        ("A-B03-011", -1)
    ]


def test_inventory_delta_rolls_back_and_surfaces_unexpected_integrity_error(
    tmp_path, monkeypatch, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)
    _patch_outbound_settings(monkeypatch, path, tmp_path)

    def fail_commit() -> None:
        raise IntegrityError("forced outbound scan failure", {}, Exception("forced"))

    monkeypatch.setattr(session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="outbound scan integrity error"):
        register_outbound_scan(
            order_no="SO202604210135",
            code="C.P.XS.000122001",
            operator_id="phone-a",
            session=session,
            quantity=1,
            location_code="A-B03-011",
            record_id=303,
        )

    assert session.exec(select(OutboundScan)).all() == []
    assert session.exec(select(InventoryLocation)).all() == []
    assert session.exec(select(InventoryMovement)).all() == []


def test_scan_api_returns_422_when_verification_record_missing(
    tmp_path, monkeypatch, client, session
) -> None:
    path = tmp_path / "outbound.xlsx"
    _prepare_workbook(path)

    from backend.app.services import outbound_reconciliation

    _patch_outbound_settings(monkeypatch, path, tmp_path)
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

    _patch_outbound_settings(monkeypatch, path, tmp_path)
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
