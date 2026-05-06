from datetime import UTC, datetime, timedelta

from openpyxl import Workbook
from sqlmodel import select

from backend.app.models import OutboundScan
from backend.app.services.auth_service import create_session, create_user
from backend.app.services.outbound_reconciliation import (
    complete_outbound_order,
    rollback_outbound_order,
)


def _prepare_workbook(path) -> None:
    workbook = Workbook()
    shipping = workbook.active
    shipping.title = "ship"
    shipping.append(["出库单号", "数量", "备件编码", "备件名称"])
    shipping.append(["SO202604210135", 2, "C.P.XS.000122001", "RTK"])
    cutting = workbook.create_sheet("cut")
    cutting.append(["数量", "备件编码", "备件名称", "库位"])
    cutting.append([2, "C.P.XS.000122001", "RTK", "A-B03-011"])
    workbook.save(path)


def test_rollback_within_window_succeeds(tmp_path, monkeypatch, session) -> None:
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
    supervisor = create_user(
        session,
        username="rollback-supervisor",
        display_name="Rollback Supervisor",
        password="rollback-supervisor-pass",
        role="supervisor",
    )

    completed = complete_outbound_order(
        order_no="SO202604210135",
        operator_id="phone-a",
        session=session,
    )
    assert completed["order_status"]["remaining_total"] == 0

    rolled = rollback_outbound_order(
        order_no="SO202604210135",
        operator=supervisor,
        session=session,
    )

    assert rolled["rolled_back"] is True
    assert rolled["voided_scan_count"] > 0
    assert rolled["order_status"]["remaining_total"] == 2
    assert rolled["snapshot"]["event"] == "rollback_completed"
    scans = session.exec(
        select(OutboundScan).where(OutboundScan.order_no == "SO202604210135")
    ).all()
    assert scans
    assert all(scan.status == "voided" for scan in scans)


def test_rollback_after_window_rejected(tmp_path, monkeypatch, session) -> None:
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
    supervisor = create_user(
        session,
        username="rollback-expired-supervisor",
        display_name="Rollback Expired Supervisor",
        password="rollback-expired-supervisor-pass",
        role="supervisor",
    )

    completed = complete_outbound_order(
        order_no="SO202604210135",
        operator_id="phone-a",
        session=session,
    )
    snapshot_id = int(completed["snapshot"]["id"])
    snapshot = session.get(outbound_reconciliation.OutboundProgressSnapshot, snapshot_id)
    assert snapshot is not None
    snapshot.completed_at = datetime.now(UTC) - timedelta(minutes=31)
    session.add(snapshot)
    session.commit()

    try:
        rollback_outbound_order(
            order_no="SO202604210135",
            operator=supervisor,
            session=session,
        )
    except RuntimeError as exc:
        assert "rollback window expired" in str(exc)
    else:
        raise AssertionError("expected rollback window rejection")


def test_rollback_api_rejects_non_supervisor(tmp_path, monkeypatch, client, session) -> None:
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
    complete_outbound_order(
        order_no="SO202604210135",
        operator_id="phone-a",
        session=session,
    )
    operator = create_user(
        session,
        username="rollback-operator",
        display_name="Rollback Operator",
        password="rollback-operator-pass",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    client.cookies.set("mlocr_session", token)

    response = client.post(
        "/api/outbound/orders/SO202604210135/rollback",
        json={"operator_id": "phone-a"},
    )
    assert response.status_code == 403
