from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.models import InventoryMovement
from backend.app.services.auth_service import create_session, create_user


def _switch_user(client: TestClient, session: Session) -> None:
    manager = create_user(
        session,
        username="summary-manager",
        display_name="summary-manager",
        password="summary-manager-pass-123",
        role="manager",
    )
    token, _ = create_session(
        session,
        manager,
        ip_address="testclient",
        user_agent="pytest",
    )
    client.cookies.set("mlocr_session", token)


def _seed_movement(
    session: Session,
    *,
    factory_id: str,
    movement_type: str,
    quantity_delta: int,
    transfer_id: str | None = None,
) -> None:
    session.add(
        InventoryMovement(
            factory_id=factory_id,
            movement_type=movement_type,
            part_key="CPXS-SUM",
            location_code="LOC-01",
            order_no=None,
            transfer_id=transfer_id,
            scan_id=None,
            quantity_delta=quantity_delta,
            before_qty=0,
            after_qty=max(quantity_delta, 0),
            operator_id="summary",
            reason="seed",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_factory_summary_report_numbers(client: TestClient, session: Session) -> None:
    _switch_user(client, session)
    _seed_movement(session, factory_id="factory_a", movement_type="inbound", quantity_delta=10)
    _seed_movement(session, factory_id="factory_a", movement_type="outbound", quantity_delta=-3)
    _seed_movement(
        session,
        factory_id="factory_a",
        movement_type="transfer_out",
        quantity_delta=-2,
        transfer_id="tf-1",
    )
    _seed_movement(
        session,
        factory_id="factory_b",
        movement_type="transfer_in",
        quantity_delta=2,
        transfer_id="tf-1",
    )
    _seed_movement(session, factory_id="factory_c", movement_type="inbound", quantity_delta=5)

    response = client.get("/api/reports/factory-summary")
    assert response.status_code == 200
    payload = response.json()
    rows = {row["factory_id"]: row for row in payload["factories"]}
    assert rows["factory_a"]["inbound"] == 10
    assert rows["factory_a"]["outbound"] == 3
    assert rows["factory_a"]["transfer_out"] == 2
    assert rows["factory_a"]["transfer_in"] == 0
    assert rows["factory_a"]["net_change"] == 5
    assert rows["factory_b"]["transfer_in"] == 2
    assert rows["factory_b"]["net_change"] == 2
    assert rows["factory_c"]["inbound"] == 5
    assert rows["factory_c"]["net_change"] == 5
    assert payload["transfers"]["count"] == 1
