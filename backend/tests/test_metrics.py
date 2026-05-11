from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.models import (
    Category,
    InventoryLocation,
    InventoryMovement,
    OutboundScan,
    Record,
    RecordStatus,
)


def add_record(
    session: Session,
    *,
    status: RecordStatus,
    category: Category = Category.A,
    confidence_score: float | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    submitted_at: datetime | None = None,
) -> Record:
    created = created_at or datetime(2026, 4, 28, 8, 0, tzinfo=UTC)
    record = Record(
        image_path=f"{status.value}.jpg",
        category=category,
        status=status,
        confidence_score=confidence_score,
        created_at=created,
        updated_at=updated_at or created,
        submitted_at=submitted_at,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_summary_empty_db_returns_zeros(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/api/metrics/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 0
    assert payload["confirmed_count"] == 0
    assert payload["submitted_count"] == 0
    assert payload["failed_count"] == 0
    assert payload["duplicates_caught"] == 0
    assert payload["by_category"] == {"A": 0, "B": 0, "C": 0}


def test_summary_counts_by_status(authenticated_client: TestClient, session: Session) -> None:
    add_record(session, status=RecordStatus.confirmed, category=Category.A)
    add_record(session, status=RecordStatus.submitted, category=Category.B)
    add_record(session, status=RecordStatus.submission_failed, category=Category.B)
    add_record(session, status=RecordStatus.duplicate, category=Category.C)

    response = authenticated_client.get("/api/metrics/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 4
    assert payload["confirmed_count"] == 2
    assert payload["submitted_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["duplicates_caught"] == 1
    assert payload["by_category"] == {"A": 1, "B": 2, "C": 1}


def test_throughput_groups_by_date(authenticated_client: TestClient, session: Session) -> None:
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    add_record(session, status=RecordStatus.uploaded, created_at=today)
    add_record(session, status=RecordStatus.confirmed, created_at=today)
    add_record(session, status=RecordStatus.submitted, created_at=yesterday)

    response = authenticated_client.get("/api/metrics/throughput", params={"days": 2})

    assert response.status_code == 200
    payload = response.json()
    by_date = {row["date"]: row for row in payload}
    assert by_date[yesterday.date().isoformat()] == {
        "date": yesterday.date().isoformat(),
        "uploaded": 1,
        "confirmed": 1,
        "submitted": 1,
    }
    assert by_date[today.date().isoformat()] == {
        "date": today.date().isoformat(),
        "uploaded": 2,
        "confirmed": 1,
        "submitted": 0,
    }


def test_ocr_quality_thresholds(authenticated_client: TestClient, session: Session) -> None:
    add_record(session, status=RecordStatus.ocr_done, confidence_score=0.95)
    add_record(session, status=RecordStatus.ocr_done, confidence_score=0.75)
    add_record(session, status=RecordStatus.needs_review, confidence_score=0.65)

    response = authenticated_client.get("/api/metrics/ocr-quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["avg_confidence"] == 0.7833
    assert payload["high_confidence_pct"] == 0.3333
    assert payload["low_confidence_pct"] == 0.3333
    assert payload["needs_review_count"] == 1


def test_savings_estimation_with_default_assumption(
    authenticated_client: TestClient,
    session: Session,
) -> None:
    created = datetime(2026, 4, 28, 8, 0, tzinfo=UTC)
    add_record(
        session,
        status=RecordStatus.confirmed,
        created_at=created,
        updated_at=created + timedelta(seconds=30),
    )
    add_record(
        session,
        status=RecordStatus.submitted,
        created_at=created,
        updated_at=created + timedelta(seconds=60),
    )

    response = authenticated_client.get("/api/metrics/savings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assume_manual_seconds_per_entry"] == 90
    assert payload["assume_avg_processing_seconds"] == 45
    assert payload["total_saved_minutes"] == 1.5


def test_metrics_all_endpoint_returns_full_payload(
    authenticated_client: TestClient,
    session: Session,
) -> None:
    add_record(session, status=RecordStatus.confirmed, confidence_score=0.91)

    response = authenticated_client.get("/api/metrics/all")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "summary",
        "throughput",
        "processing_time",
        "ocr_quality",
        "error_prevention",
        "logistics",
        "savings",
        "generated_at",
    }
    assert payload["summary"]["confirmed_count"] == 1
    assert len(payload["throughput"]) == 30


def test_logistics_metrics_summarize_inventory_and_outbound_activity(
    authenticated_client: TestClient,
    session: Session,
) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            InventoryLocation(
                part_key="CPXS000122001",
                location_code="A-01",
                quantity=5,
                status="active",
                zero_stock=False,
            ),
            InventoryLocation(
                part_key="CPXS000122001",
                location_code="A-02",
                quantity=0,
                status="active",
                zero_stock=True,
            ),
            InventoryLocation(
                part_key="CPXS000122002",
                location_code="B-01",
                quantity=9,
                status="disabled",
                zero_stock=False,
            ),
            InventoryMovement(
                movement_type="inbound",
                part_key="CPXS000122001",
                location_code="A-01",
                quantity_delta=5,
                before_qty=0,
                after_qty=5,
                created_at=now,
            ),
            InventoryMovement(
                movement_type="transfer_out",
                part_key="CPXS000122001",
                location_code="A-02",
                quantity_delta=-2,
                before_qty=2,
                after_qty=0,
                created_at=now - timedelta(days=9),
            ),
            OutboundScan(
                order_no="SO202605070001",
                part_code="CPXS000122001",
                source_code="CPXS000122001",
                matched_code="CPXS000122001",
                quantity=3,
                status="active",
            ),
            OutboundScan(
                order_no="SO202605070002",
                part_code="CPXS000122002",
                source_code="CPXS000122002",
                matched_code="CPXS000122002",
                quantity=4,
                status="void",
            ),
        ]
    )
    session.commit()

    response = authenticated_client.get("/api/metrics/logistics", params={"days": 7})

    assert response.status_code == 200
    payload = response.json()
    assert payload["inventory"] == {
        "location_count": 3,
        "active_location_count": 2,
        "disabled_location_count": 1,
        "zero_stock_location_count": 1,
        "restock_needed_count": 1,
        "part_count": 2,
        "total_quantity": 14,
    }
    assert payload["movements"] == {
        "days": 7,
        "movement_count": 1,
        "inbound_quantity": 5,
        "outbound_quantity": 0,
        "transfer_quantity": 0,
    }
    assert payload["outbound"] == {
        "active_scan_count": 1,
        "active_scan_quantity": 3,
        "active_order_count": 1,
    }


def test_metrics_require_login(client: TestClient) -> None:
    for path in (
        "/api/metrics/summary",
        "/api/metrics/throughput",
        "/api/metrics/processing-time",
        "/api/metrics/ocr-quality",
        "/api/metrics/savings",
        "/api/metrics/logistics",
        "/api/metrics/all",
    ):
        response = client.get(path)
        assert response.status_code == 401
