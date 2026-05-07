from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryLocation, InventoryMovement
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)


def _seed_location(
    session: Session,
    *,
    factory_id: str,
    part_key: str,
    location_code: str,
    quantity: int,
) -> None:
    row = InventoryLocation(
        factory_id=factory_id,
        part_key=part_key,
        location_code=location_code,
        quantity=quantity,
        status="active",
        zero_stock=quantity <= 0,
    )
    session.add(row)
    session.commit()


def _switch_supervisor(client: TestClient, session: Session) -> None:
    manager = create_user(
        session,
        username="xfer-manager",
        display_name="xfer-manager",
        password="xfer-manager-pass-123",
        role="manager",
    )
    supervisor = create_user(
        session,
        username="xfer-supervisor",
        display_name="xfer-supervisor",
        password="xfer-supervisor-pass-123",
        role="supervisor",
        actor=manager,
    )
    token, _ = create_session(
        session,
        supervisor,
        ip_address="testclient",
        user_agent="pytest",
    )
    csrf_token = "pytest-csrf-token"
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf_token)
    client.headers.update({CSRF_HEADER: csrf_token})


def test_transfer_success_creates_linked_movements(client: TestClient, session: Session) -> None:
    _switch_supervisor(client, session)
    _seed_location(
        session,
        factory_id="factory_a",
        part_key="CPXS000122001",
        location_code="A-01",
        quantity=10,
    )

    response = client.post(
        "/api/transfers",
        json={
            "source_factory": "factory_a",
            "target_factory": "factory_b",
            "part_key": "C.P.XS.000122001",
            "quantity": 4,
            "reason": "line_balance",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    transfer_id = payload["transfer_id"]
    assert transfer_id
    assert payload["source_location"]["quantity"] == 6
    assert payload["target_location"]["quantity"] == 4

    movements = session.exec(
        select(InventoryMovement).where(InventoryMovement.transfer_id == transfer_id)
    ).all()
    assert len(movements) == 2
    assert sorted(movement.movement_type for movement in movements) == [
        "transfer_in",
        "transfer_out",
    ]


def test_transfer_idempotency_key_prevents_duplicate_stock_moves(
    client: TestClient,
    session: Session,
) -> None:
    _switch_supervisor(client, session)
    _seed_location(
        session,
        factory_id="factory_a",
        part_key="CPXS000122099",
        location_code="A-99",
        quantity=10,
    )
    payload = {
        "source_factory": "factory_a",
        "target_factory": "factory_b",
        "part_key": "CPXS000122099",
        "quantity": 4,
        "reason": "line_balance",
        "idempotency_key": "transfer-click-001",
    }

    first = client.post("/api/transfers", json=payload)
    second = client.post("/api/transfers", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["transfer_id"] == second.json()["transfer_id"]
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    source_after = session.exec(
        select(InventoryLocation).where(
            InventoryLocation.factory_id == "factory_a",
            InventoryLocation.part_key == "CPXS000122099",
            InventoryLocation.location_code == "A-99",
        )
    ).one()
    assert int(source_after.quantity) == 6
    movements = session.exec(
        select(InventoryMovement).where(
            InventoryMovement.part_key == "CPXS000122099",
            InventoryMovement.transfer_id == first.json()["transfer_id"],
        )
    ).all()
    assert len(movements) == 2


def test_transfer_rejects_insufficient_inventory(client: TestClient, session: Session) -> None:
    _switch_supervisor(client, session)
    _seed_location(
        session,
        factory_id="factory_a",
        part_key="CPXS000122002",
        location_code="A-02",
        quantity=1,
    )

    response = client.post(
        "/api/transfers",
        json={
            "source_factory": "factory_a",
            "target_factory": "factory_b",
            "part_key": "CPXS000122002",
            "quantity": 3,
            "reason": "line_balance",
        },
    )
    assert response.status_code == 409
    assert "insufficient inventory" in response.json()["detail"]


def test_transfer_is_atomic_when_target_disabled(client: TestClient, session: Session) -> None:
    _switch_supervisor(client, session)
    _seed_location(
        session,
        factory_id="factory_a",
        part_key="CPXS000122003",
        location_code="A-03",
        quantity=5,
    )
    target = InventoryLocation(
        factory_id="factory_b",
        part_key="CPXS000122003",
        location_code="B-03",
        quantity=0,
        status="disabled",
        zero_stock=True,
    )
    session.add(target)
    session.commit()

    response = client.post(
        "/api/transfers",
        json={
            "source_factory": "factory_a",
            "target_factory": "factory_b",
            "part_key": "CPXS000122003",
            "quantity": 2,
            "reason": "line_balance",
        },
    )
    assert response.status_code == 409
    assert "target location disabled" in response.json()["detail"]

    source_after = session.exec(
        select(InventoryLocation).where(
            InventoryLocation.factory_id == "factory_a",
            InventoryLocation.part_key == "CPXS000122003",
            InventoryLocation.location_code == "A-03",
        )
    ).one()
    assert int(source_after.quantity) == 5
    assert (
        session.exec(
            select(InventoryMovement).where(InventoryMovement.part_key == "CPXS000122003")
        ).all()
        == []
    )
    assert session.exec(select(AuditLog).where(AuditLog.action == "inventory.transfer")).all() == []
