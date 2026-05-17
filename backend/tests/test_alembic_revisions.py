from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import create_engine

from backend.app.database import _ensure_outbound_scan_record_index
from backend.app.models import OutboundScan


def test_alembic_revision_ids_fit_postgres_version_column() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    for migration_path in versions_dir.glob("*.py"):
        namespace: dict[str, object] = {}
        exec(migration_path.read_text(encoding="utf-8"), namespace)
        revision = namespace.get("revision")
        if isinstance(revision, str):
            assert len(revision) <= 32, f"{migration_path.name} revision id is too long"


def test_alembic_down_revisions_point_to_existing_revision_ids() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    revisions: dict[str, str] = {}
    down_revisions: dict[str, object] = {}
    for migration_path in versions_dir.glob("*.py"):
        namespace: dict[str, Any] = {}
        exec(migration_path.read_text(encoding="utf-8"), namespace)
        revision = namespace.get("revision")
        if isinstance(revision, str):
            revisions[revision] = migration_path.name
            down_revisions[revision] = namespace.get("down_revision")

    missing: dict[str, list[str]] = {}
    for revision, down_revision in down_revisions.items():
        if down_revision is None:
            continue
        parents = [down_revision] if isinstance(down_revision, str) else list(down_revision)
        missing_parents = [parent for parent in parents if parent not in revisions]
        if missing_parents:
            missing[revision] = missing_parents

    assert missing == {}


def test_outbound_scan_record_idempotency_index_is_declared_in_model() -> None:
    index = next(
        item for item in OutboundScan.__table__.indexes if item.name == "ux_outbound_scans_record"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["order_no", "part_code", "record_id"]
    assert str(index.dialect_options["sqlite"]["where"]) == (
        "record_id IS NOT NULL AND status = 'active'"
    )


def test_runtime_database_repair_ensures_outbound_scan_idempotency_index() -> None:
    database_module = Path(__file__).resolve().parents[2] / "backend" / "app" / "database.py"
    database_source = database_module.read_text(encoding="utf-8")

    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_outbound_scans_record" in database_source
    assert "ON outbound_scans(order_no, part_code, record_id)" in database_source
    assert "WHERE record_id IS NOT NULL AND status = 'active'" in database_source
    assert "_deduplicate_outbound_scan_records(conn, columns)" in database_source


def test_runtime_database_repair_voids_duplicate_active_record_scans(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE outbound_scans (
                    id INTEGER PRIMARY KEY,
                    order_no TEXT NOT NULL,
                    part_code TEXT NOT NULL,
                    record_id INTEGER,
                    status TEXT NOT NULL,
                    void_reason TEXT,
                    voided_by TEXT,
                    voided_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO outbound_scans
                    (id, order_no, part_code, record_id, status)
                VALUES
                    (1, 'SO1', 'PART1', 42, 'active'),
                    (2, 'SO1', 'PART1', 42, 'active'),
                    (3, 'SO1', 'PART1', 43, 'active')
                """
            )
        )
        columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(outbound_scans)")).fetchall()
        }

        _ensure_outbound_scan_record_index(conn, columns)

        rows = conn.execute(
            text(
                """
                SELECT id, status, void_reason, voided_by, voided_at
                FROM outbound_scans
                ORDER BY id
                """
            )
        ).mappings()
        by_id = {row["id"]: dict(row) for row in rows}
        indexes = conn.execute(text("PRAGMA index_list(outbound_scans)")).fetchall()

    assert by_id[1]["status"] == "active"
    assert by_id[2]["status"] == "voided"
    assert by_id[2]["void_reason"] == "duplicate active record_id before idempotency index"
    assert by_id[2]["voided_by"] == "system"
    assert by_id[2]["voided_at"] is not None
    assert by_id[3]["status"] == "active"
    assert any(row[1] == "ux_outbound_scans_record" for row in indexes)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO outbound_scans
                        (order_no, part_code, record_id, status)
                    VALUES
                        ('SO1', 'PART1', 42, 'active')
                    """
                )
            )
