from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.models import Category, Record, RecordStatus


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


def test_summary_empty_db_returns_zeros(client: TestClient) -> None:
    response = client.get("/api/metrics/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 0
    assert payload["confirmed_count"] == 0
    assert payload["submitted_count"] == 0
    assert payload["failed_count"] == 0
    assert payload["duplicates_caught"] == 0
    assert payload["by_category"] == {"A": 0, "B": 0, "C": 0}


def test_summary_counts_by_status(client: TestClient, session: Session) -> None:
    add_record(session, status=RecordStatus.confirmed, category=Category.A)
    add_record(session, status=RecordStatus.submitted, category=Category.B)
    add_record(session, status=RecordStatus.submission_failed, category=Category.B)
    add_record(session, status=RecordStatus.duplicate, category=Category.C)

    response = client.get("/api/metrics/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 4
    assert payload["confirmed_count"] == 2
    assert payload["submitted_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["duplicates_caught"] == 1
    assert payload["by_category"] == {"A": 1, "B": 2, "C": 1}


def test_throughput_groups_by_date(client: TestClient, session: Session) -> None:
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    add_record(session, status=RecordStatus.uploaded, created_at=today)
    add_record(session, status=RecordStatus.confirmed, created_at=today)
    add_record(session, status=RecordStatus.submitted, created_at=yesterday)

    response = client.get("/api/metrics/throughput", params={"days": 2})

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


def test_ocr_quality_thresholds(client: TestClient, session: Session) -> None:
    add_record(session, status=RecordStatus.ocr_done, confidence_score=0.95)
    add_record(session, status=RecordStatus.ocr_done, confidence_score=0.75)
    add_record(session, status=RecordStatus.needs_review, confidence_score=0.65)

    response = client.get("/api/metrics/ocr-quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["avg_confidence"] == 0.7833
    assert payload["high_confidence_pct"] == 0.3333
    assert payload["low_confidence_pct"] == 0.3333
    assert payload["needs_review_count"] == 1


def test_savings_estimation_with_default_assumption(client: TestClient, session: Session) -> None:
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

    response = client.get("/api/metrics/savings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assume_manual_seconds_per_entry"] == 90
    assert payload["assume_avg_processing_seconds"] == 45
    assert payload["total_saved_minutes"] == 1.5


def test_metrics_all_endpoint_returns_full_payload(client: TestClient, session: Session) -> None:
    add_record(session, status=RecordStatus.confirmed, confidence_score=0.91)

    response = client.get("/api/metrics/all")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "summary",
        "throughput",
        "processing_time",
        "ocr_quality",
        "error_prevention",
        "savings",
        "generated_at",
    }
    assert payload["summary"]["confirmed_count"] == 1
    assert len(payload["throughput"]) == 30
