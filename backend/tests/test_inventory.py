from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryLocation, InventoryMovement
from backend.app.services import outbound_reconciliation
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


def _login_operator(
    client: TestClient, session: Session, username: str = "inventory-operator"
) -> None:
    user = create_user(
        session,
        username=username,
        display_name="Inventory Operator",
        password=f"{username}-pass",
        role="operator",
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
    part_name: str | None = None,
    location_kind: str = "permanent",
    factory_id: str = "factory_a",
) -> InventoryLocation:
    row = InventoryLocation(
        factory_id=factory_id,
        part_key=part_key,
        part_name=part_name,
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


def test_inventory_accepts_legacy_long_term_locations(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122100",
        location_code="LT-01",
        quantity=4,
        location_kind="long_term",
    )

    response = client.get("/api/inventory/locations")

    assert response.status_code == 200
    location = response.json()["locations"][0]
    assert location["id"] == row.id
    assert location["location_kind"] == "permanent"


def test_inventory_locations_include_location_profile(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    _seed_location(
        session,
        part_key="CPXS000122102",
        location_code="A-A01-011",
        quantity=4,
        location_kind="permanent",
    )

    response = client.get("/api/inventory/locations")

    assert response.status_code == 200
    location = response.json()["locations"][0]
    assert location["location_code"] == "A-A01-011"
    assert location["location_profile"]["parse_status"] == "standard"
    assert location["location_profile"]["zone"] == "A"
    assert location["location_profile"]["aisle_or_column"] == "A"
    assert location["location_profile"]["rack_index"] == 1
    assert location["location_profile"]["level"] == 1
    assert location["location_profile"]["depth"] == 1
    assert location["location_profile"]["centerline_rank"] == 1


def test_inventory_location_map_requires_login(client: TestClient) -> None:
    response = client.get("/api/inventory/location-map")

    assert response.status_code == 401


def test_inventory_location_map_allows_operator_login(
    client: TestClient,
    session: Session,
) -> None:
    _login_operator(client, session)
    _seed_location(
        session,
        part_key="CPXS000122104",
        location_code="A-A01-011",
        quantity=4,
    )

    response = client.get("/api/inventory/location-map")

    assert response.status_code == 200
    assert response.json()["summary"]["standard_location_count"] == 1


def test_inventory_locations_require_login_and_allow_operator(
    client: TestClient,
    session: Session,
) -> None:
    _seed_location(
        session,
        part_key="CPXS000122105",
        location_code="A-A01-011",
        quantity=4,
    )

    assert client.get("/api/inventory/locations").status_code == 401

    _login_operator(client, session)
    response = client.get("/api/inventory/locations")

    assert response.status_code == 200
    assert response.json()["locations"][0]["part_key"] == "CPXS000122105"


def test_inventory_location_map_endpoint_returns_aggregated_cells(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    _seed_location(
        session,
        part_key="CPXS000122103",
        part_name="Mapped Part",
        location_code="A-A01-011",
        quantity=4,
    )

    response = client.get("/api/inventory/location-map")

    assert response.status_code == 200
    payload = response.json()
    cell = payload["zones"]["A"]["columns"]["A"]["racks"]["1"]["levels"]["1"]["depths"]["1"]
    assert cell["location_code"] == "A-A01-011"
    assert cell["location_profile"]["parse_status"] == "standard"
    assert cell["materials"] == [
        {"part_key": "CPXS000122103", "part_name": "Mapped Part", "quantity": 4}
    ]


def test_operator_can_move_inventory_and_is_recorded_as_operator(
    client: TestClient,
    session: Session,
) -> None:
    _login_operator(client, session, username="inventory-mover")
    source = _seed_location(
        session,
        part_key="CPXS000122106",
        location_code="A-A01-011",
        quantity=8,
        location_kind="permanent",
    )

    response = client.post(
        "/api/inventory/move",
        json={
            "source_location_id": source.id,
            "target_location_code": "A-A01-012",
            "quantity": 3,
            "target_location_kind": "permanent",
            "reason": "operator shelf transfer",
        },
    )

    assert response.status_code == 200
    movement_ids = [row["operator_id"] for row in response.json()["movements"]]
    assert movement_ids == ["inventory-mover", "inventory-mover"]
    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122106")
    ).all()
    assert {row.operator_id for row in movements} == {"inventory-mover"}


def test_operator_cannot_manually_adjust_inventory_quantity(
    client: TestClient,
    session: Session,
) -> None:
    _login_operator(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122107",
        location_code="A-A01-011",
        quantity=4,
    )

    response = client.patch(
        f"/api/inventory/locations/{row.id}",
        json={"quantity": 6, "reason": "operator correction attempt"},
    )

    assert response.status_code == 403
    stored = session.get(InventoryLocation, row.id)
    assert stored is not None
    assert stored.quantity == 4


def test_inventory_adjust_preserves_pending_status(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122101",
        location_code="PEND-01",
        quantity=4,
        location_kind="permanent",
    )
    row.status = "pending_replacement"
    session.add(row)
    session.commit()

    response = client.patch(
        f"/api/inventory/locations/{row.id}",
        json={"quantity": 6, "reason": "count correction"},
    )

    assert response.status_code == 200
    assert response.json()["location"]["status"] == "pending_replacement"
    stored = session.get(InventoryLocation, row.id)
    assert stored is not None
    assert stored.status == "pending_replacement"


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


def test_inventory_move_allows_variance_and_records_adjustment(
    client: TestClient,
    session: Session,
) -> None:
    _login_operator(client, session, username="inventory-variance-operator")
    source = _seed_location(
        session,
        part_key="CPXS000122040",
        location_code="A-40",
        quantity=10,
        location_kind="permanent",
    )
    _seed_location(
        session,
        part_key="CPXS000122040",
        location_code="B-40",
        quantity=2,
        location_kind="permanent",
    )

    response = client.post(
        "/api/inventory/move",
        json={
            "source_location_id": source.id,
            "target_location_code": "B-40",
            "quantity": 12,
            "target_location_kind": "permanent",
            "reason": "现场调拨补录",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_location"]["quantity"] == 0
    assert payload["target_location"]["quantity"] == 14

    movements = session.exec(
        select(InventoryMovement)
        .where(InventoryMovement.part_key == "CPXS000122040")
        .order_by(InventoryMovement.id.asc())
    ).all()
    assert [row.movement_type for row in movements] == [
        "manual_adjust",
        "manual_move_out",
        "manual_move_in",
    ]
    adjust = movements[0]
    assert adjust.before_qty == 10
    assert adjust.after_qty == 12
    assert adjust.quantity_delta == 2
    assert "盘点发现差异" in (adjust.reason or "")
    assert adjust.operator_id == "inventory-variance-operator"


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


def test_outbound_inbound_returns_quantity_on_hand_and_records_movement(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)

    response = client.post(
        "/api/outbound/inventory/inbound",
        json={
            "part_key": "CPXS000122006",
            "location_code": "QA-IN-06",
            "quantity": 7,
            "operator_id": "spoofed-operator",
            "reason": "purchase_inbound_test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] is True
    assert payload["location"]["quantity"] == 7
    assert payload["location"]["quantity_on_hand"] == 7
    assert payload["movement"]["movement_type"] == "inbound"
    assert payload["movement"]["before_qty"] == 0
    assert payload["movement"]["after_qty"] == 7
    assert payload["movement"]["operator_id"] == "inventory-supervisor"
    movement = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122006")
    ).one()
    assert movement.operator_id == "inventory-supervisor"
    assert movement.reason == "purchase_inbound_test"


def test_outbound_inbound_rejects_non_positive_quantity(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)

    for quantity in (0, -3):
        response = client.post(
            "/api/outbound/inventory/inbound",
            json={
                "part_key": "CPXS000122007",
                "location_code": "QA-IN-07",
                "quantity": quantity,
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "quantity must be > 0"
    assert (
        session.exec(
            select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122007")
        ).first()
        is None
    )


def test_outbound_inbound_rolls_back_location_when_movement_fails(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    _login_supervisor(client, session)

    def fail_movement(*args, **kwargs):
        raise RuntimeError("movement write failed")

    monkeypatch.setattr(outbound_reconciliation, "_record_inventory_movement", fail_movement)

    response = client.post(
        "/api/outbound/inventory/inbound",
        json={
            "part_key": "CPXS000122008",
            "location_code": "QA-IN-08",
            "quantity": 4,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "movement write failed"
    assert (
        session.exec(
            select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122008")
        ).first()
        is None
    )
    assert session.exec(select(InventoryMovement)).all() == []


def test_outbound_inbound_idempotency_key_prevents_duplicate_stock_moves(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    payload = {
        "part_key": "CPXS000122009",
        "location_code": "QA-IN-09",
        "quantity": 6,
        "reason": "purchase_inbound_test",
        "idempotency_key": "inbound-click-001",
    }

    first = client.post("/api/outbound/inventory/inbound", json=payload)
    second = client.post("/api/outbound/inventory/inbound", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["movement"]["id"] == second.json()["movement"]["id"]
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122009")
    ).one()
    assert location.quantity == 6
    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122009")
    ).all()
    assert len(movements) == 1
    audits = session.exec(select(AuditLog).where(AuditLog.action == "inventory.inbound")).all()
    assert len(audits) == 1


def test_outbound_inbound_idempotency_key_rejects_changed_payload(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    first = client.post(
        "/api/outbound/inventory/inbound",
        json={
            "part_key": "CPXS000122010",
            "location_code": "QA-IN-10",
            "quantity": 3,
            "reason": "purchase_inbound_test",
            "idempotency_key": "inbound-click-002",
        },
    )
    changed = client.post(
        "/api/outbound/inventory/inbound",
        json={
            "part_key": "CPXS000122010",
            "location_code": "QA-IN-10",
            "quantity": 4,
            "reason": "purchase_inbound_test",
            "idempotency_key": "inbound-click-002",
        },
    )

    assert first.status_code == 200
    assert changed.status_code == 409
    assert "idempotency_key reused with different inbound payload" in changed.json()["detail"]
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122010")
    ).one()
    assert location.quantity == 3


def test_outbound_inbound_blank_idempotency_key_is_treated_as_missing(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    payload = {
        "part_key": "CPXS000122011",
        "location_code": "QA-IN-11",
        "quantity": 5,
        "reason": "purchase_inbound_test",
        "idempotency_key": "   ",
    }

    first = client.post("/api/outbound/inventory/inbound", json=payload)
    second = client.post("/api/outbound/inventory/inbound", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["movement"]["id"] != second.json()["movement"]["id"]
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122011")
    ).one()
    assert location.quantity == 10


def test_outbound_inbound_idempotency_key_is_scoped_by_operator(
    client: TestClient,
    session: Session,
) -> None:
    _login_supervisor(client, session)
    payload = {
        "part_key": "CPXS000122012",
        "location_code": "QA-IN-12",
        "quantity": 5,
        "reason": "purchase_inbound_test",
        "idempotency_key": "shared-inbound-click",
    }
    first = client.post("/api/outbound/inventory/inbound", json=payload)
    second_user = create_user(
        session,
        username="inventory-supervisor-two",
        display_name="Inventory Supervisor Two",
        password="inventory-supervisor-two-pass",
        role="supervisor",
    )
    token, _ = create_session(session, second_user, ip_address="testclient", user_agent="pytest")
    client.cookies.set(SESSION_COOKIE, token)

    second = client.post("/api/outbound/inventory/inbound", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["movement"]["id"] != second.json()["movement"]["id"]
    location = session.exec(
        select(InventoryLocation).where(InventoryLocation.part_key == "CPXS000122012")
    ).one()
    assert location.quantity == 10


def test_inventory_manual_adjust_requires_supervisor(client: TestClient, session: Session) -> None:
    _login_operator(client, session)
    row = _seed_location(
        session,
        part_key="CPXS000122013",
        location_code="QA-IN-13",
        quantity=5,
    )

    assert (
        client.patch(
            f"/api/inventory/locations/{row.id}",
            json={"quantity": 6, "reason": "operator adjustment blocked"},
        ).status_code
        == 403
    )
