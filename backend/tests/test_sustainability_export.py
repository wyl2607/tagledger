from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from sqlmodel import Session

from backend.app.models import InventoryMovement, OutboundProgressSnapshot, OutboundScan, Record
from scripts.export_sustainability_snapshot import run_export


def _seed_snapshot_rows(session: Session) -> None:
    record = Record(
        factory_id="factory_a",
        image_path="/tmp/a.png",
        category="A",
        model="x1",
        vin_or_bin="VIN-123",
        serial_number="SN-123",
        operator_id="alice-supervisor",
        raw_ocr_text="sensitive",
        confidence_score=0.98,
        status="duplicate",
        submission_attempts=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(record)
    session.commit()

    scan = OutboundScan(
        factory_id="factory_a",
        order_no="SO-001",
        part_code="CPXS001",
        location_code="A-01",
        source_code="SRC-001",
        matched_code="CPXS001",
        quantity=2,
        status="voided",
        operator_id="worker-01",
        batch_id="b-1",
        transfer_id="tf-1",
        record_id=record.id,
        void_reason="retry",
        voided_by="manager-01",
        voided_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    movement = InventoryMovement(
        factory_id="factory_a",
        movement_type="transfer_out",
        part_key="CPXS001",
        location_code="A-01",
        order_no="SO-001",
        transfer_id="tf-1",
        scan_id=1,
        quantity_delta=-2,
        before_qty=10,
        after_qty=8,
        operator_id="worker-01",
        reason="balance",
        created_at=datetime.now(UTC),
    )
    progress = OutboundProgressSnapshot(
        factory_id="factory_a",
        order_no="SO-001",
        event="scan",
        required_total=10,
        scanned_total=2,
        remaining_total=8,
        line_total=2,
        complete_line_total=0,
        active_scan_count=1,
        active_scan_quantity=2,
        operator_id="worker-01",
        batch_id="b-1",
        scan_id=1,
        detail_json=json.dumps(
            {
                "note": "ok",
                "raw_ocr_text": "should_remove",
                "operator_id": "worker-01",
                "vin_or_bin": "VIN-123",
            },
            ensure_ascii=False,
        ),
        created_at=datetime.now(UTC),
    )
    session.add(scan)
    session.add(movement)
    session.add(progress)
    session.commit()


def test_export_snapshot_parquet_and_manifest(session: Session, tmp_path: Path) -> None:
    _seed_snapshot_rows(session)
    output_dir = tmp_path / "snapshots"
    database_url = str(session.get_bind().url)
    manifest = run_export(
        output_dir=output_dir,
        snapshot_date=date(2026, 5, 5),
        database_url=database_url,
    )

    assert (output_dir / "_manifest.json").exists()
    for name in ("outbound_scans", "inventory_movements", "progress_snapshots", "records"):
        assert (output_dir / f"{name}.parquet").exists()
        assert manifest["tables"][name]["row_count"] >= 1

    scans_df = pd.read_parquet(output_dir / "outbound_scans.parquet")
    assert "operator_id" not in scans_df.columns
    assert "voided_by" not in scans_df.columns
    assert "operator_role" in scans_df.columns
    assert "voided_by_role" in scans_df.columns
    assert scans_df.loc[0, "operator_role"] == "operator"
    assert scans_df.loc[0, "voided_by_role"] == "supervisor"

    movements_df = pd.read_parquet(output_dir / "inventory_movements.parquet")
    assert "operator_id" not in movements_df.columns
    assert movements_df.loc[0, "operator_role"] == "operator"

    progress_df = pd.read_parquet(output_dir / "progress_snapshots.parquet")
    detail = progress_df.loc[0, "detail_json"]
    assert detail
    detail_payload = json.loads(detail)
    assert "raw_ocr_text" not in detail_payload
    assert "operator_id" not in detail_payload
    assert "vin_or_bin" not in detail_payload

    records_df = pd.read_parquet(output_dir / "records.parquet")
    assert "operator_id" not in records_df.columns
    assert "vin_or_bin" not in records_df.columns
    assert "serial_number" not in records_df.columns
    assert "raw_ocr_text" not in records_df.columns
    assert "image_path" not in records_df.columns
    assert records_df.loc[0, "status"] == "duplicate"

    manifest_data = json.loads((output_dir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["snapshot_date"] == "2026-05-05"
    assert "generated_at" in manifest_data
    assert "git_commit" in manifest_data
    assert set(manifest_data["tables"].keys()) == {
        "outbound_scans",
        "inventory_movements",
        "progress_snapshots",
        "records",
    }
