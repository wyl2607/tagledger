from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import InventoryLocation, InventoryMovement
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)


def _login_supervisor(client: TestClient, session: Session) -> None:
    user = create_user(
        session,
        username="inventory-supervisor",
        display_name="Inventory Supervisor",
        password="inventory-supervisor-pass",
        role="supervisor",
    )
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, "pytest-csrf-token")
    client.headers.update({CSRF_HEADER: "pytest-csrf-token"})


def _seed_location(
    session: Session,
    *,
    part_key: str,
    location_code: str,
    quantity: int,
    location_kind: str = "permanent",
    factory_id: str = "factory_a",
) -> InventoryLocation:
    row = InventoryLocation(
        factory_id=factory_id,
        part_key=part_key,
        location_code=location_code,
        quantity=quantity,
        status="active" if quantity > 0 else "zero_stock",
        zero_stock=quantity <= 0,
        location_kind=location_kind,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_inventory_list_hides_retired_temporary_locations(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    visible = _seed_location(
        session,
        part_key="CPXS000122001",
        location_code="A-01",
        quantity=5,
    )
    retired = _seed_location(
        session,
        part_key="CPXS000122001",
        location_code="TMP-01",
        quantity=0,
        location_kind="temporary",
    )
    retired.status = "retired"
    session.add(retired)
    session.commit()

    response = client.get("/api/inventory/locations")

    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["locations"]] == [visible.id]
    assert payload["summary"]["visible_location_count"] == 1
    assert payload["summary"]["retired_location_count"] == 1


def test_inventory_adjust_retire_temporary_and_records_movement(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122002",
        location_code="TMP-02",
        quantity=3,
        location_kind="temporary",
    )

    response = client.patch(
        f"/api/inventory/locations/{row.id}",
        json={"quantity": 0, "reason": "temporary bin consumed"},
    )

    assert response.status_code == 200
    location = response.json()["location"]
    assert location["quantity"] == 0
    assert location["status"] == "retired"
    assert location["visible"] is False
    stored = session.get(InventoryLocation, row.id)
    assert stored is not None
    assert stored.status == "retired"
    movement = session.exec(select(InventoryMovement)).one()
    assert movement.movement_type == "manual_adjust"
    assert movement.before_qty == 3
    assert movement.after_qty == 0


def test_inventory_adjust_permanent_zero_stays_visible_with_warning(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122003",
        location_code="P-03",
        quantity=2,
        location_kind="permanent",
    )

    response = client.patch(
        f"/api/inventory/locations/{row.id}",
        json={"quantity": 0, "reason": "counted empty"},
    )

    assert response.status_code == 200
    location = response.json()["location"]
    assert location["status"] == "zero_stock"
    assert location["visible"] is True
    assert location["restock_required"] is True


def test_inventory_move_updates_both_locations_and_preserves_movements(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    source = _seed_location(
        session,
        part_key="CPXS000122004",
        location_code="A-04",
        quantity=8,
        location_kind="permanent",
    )

    response = client.post(
        "/api/inventory/move",
        json={
            "source_location_id": source.id,
            "target_location_code": "B-04",
            "quantity": 5,
            "target_location_kind": "temporary",
            "reason": "visual map move",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_location"]["quantity"] == 3
    assert payload["target_location"]["quantity"] == 5
    assert payload["target_location"]["location_kind"] == "temporary"
    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122004")
    ).all()
    assert sorted(row.movement_type for row in movements) == ["manual_move_in", "manual_move_out"]


def test_inventory_move_rejects_same_location(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    source = _seed_location(
        session,
        part_key="CPXS000122005",
        location_code="A-05",
        quantity=8,
        location_kind="permanent",
    )

    response = client.post(
        "/api/inventory/move",
        json={
            "source_location_id": source.id,
            "target_location_code": "a-05",
            "quantity": 2,
            "target_location_kind": "permanent",
            "reason": "same shelf mistake",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "target location must differ from source location"


def test_inventory_api_requires_supervisor(client: TestClient, session: Session) -> None:
    operator = create_user(
        session,
        username="inventory-operator",
        display_name="Inventory Operator",
        password="inventory-operator-pass",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, "pytest-csrf-token")
    client.headers.update({CSRF_HEADER: "pytest-csrf-token"})

    assert client.get("/api/inventory/locations").status_code == 403
