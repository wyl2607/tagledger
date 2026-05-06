#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

try:
    import pandas as pd
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: pandas. Install with '.venv/bin/pip install pandas pyarrow'."
    ) from exc

from sqlalchemy import create_engine, text

from scripts.lib.anonymize import map_operator_to_role, redact_detail_json

ROOT_DIR = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export anonymized sustainability snapshot parquet files."
    )
    parser.add_argument(
        "--output-dir",
        default="data/snapshots",
        help="Snapshot output directory (default: data/snapshots)",
    )
    parser.add_argument(
        "--snapshot-date",
        default="",
        help="Snapshot date in YYYY-MM-DD (default: today UTC)",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional DB URL override. Defaults to backend settings database URL.",
    )
    return parser.parse_args()


def _resolve_snapshot_date(raw_value: str) -> date:
    if not raw_value:
        return datetime.now(UTC).date()
    return datetime.strptime(raw_value, "%Y-%m-%d").date()  # noqa: DTZ007


def _normalize_database_url(url: str) -> str:
    raw_url = (url or "").strip()
    for prefix in ("postgresql://", "postgres://"):
        if raw_url.startswith(prefix):
            return raw_url.replace(prefix, "postgresql+psycopg://", 1)
    return raw_url


def _load_default_database_url() -> str:
    env_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_DSN")
    if env_url:
        return _normalize_database_url(env_url)
    default_url = "sqlite:///data/app.db"
    config_path = ROOT_DIR / "config" / "settings.yaml"
    if not config_path.exists():
        return default_url
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    app_config = dict(payload.get("app", {}))
    database_config = payload.get("database", {}) or {}
    configured = (
        app_config.get("database_dsn")
        or database_config.get("dsn")
        or app_config.get("database_url")
        or default_url
    )
    return _normalize_database_url(str(configured))


def _table_columns() -> dict[str, list[str]]:
    return {
        "outbound_scans": [
            "id",
            "factory_id",
            "order_no",
            "part_code",
            "location_code",
            "source_code",
            "matched_code",
            "quantity",
            "status",
            "operator_id",
            "batch_id",
            "transfer_id",
            "record_id",
            "verification_record_id",
            "void_reason",
            "voided_by",
            "voided_at",
            "created_at",
        ],
        "inventory_movements": [
            "id",
            "factory_id",
            "movement_type",
            "part_key",
            "location_code",
            "order_no",
            "transfer_id",
            "scan_id",
            "quantity_delta",
            "before_qty",
            "after_qty",
            "operator_id",
            "reason",
            "created_at",
        ],
        "progress_snapshots": [
            "id",
            "factory_id",
            "order_no",
            "event",
            "required_total",
            "scanned_total",
            "remaining_total",
            "line_total",
            "complete_line_total",
            "active_scan_count",
            "active_scan_quantity",
            "operator_id",
            "batch_id",
            "scan_id",
            "completed_at",
            "detail_json",
            "created_at",
        ],
        "records": [
            "id",
            "factory_id",
            "category",
            "model",
            "operator_id",
            "confidence_score",
            "status",
            "submission_attempts",
            "last_error",
            "created_at",
            "updated_at",
            "submitted_at",
        ],
    }


def _available_columns(conn, source_table_name: str) -> set[str]:
    dialect_name = conn.engine.dialect.name
    if dialect_name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({source_table_name})")).mappings().all()
        return {str(row["name"]) for row in rows}
    rows = conn.execute(
        text(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": source_table_name},
    ).mappings()
    return {str(row["column_name"]) for row in rows}


def _build_select(
    source_table_name: str, target_name: str, wanted_columns: list[str], present_columns: set[str]
) -> str:
    selected = [column for column in wanted_columns if column in present_columns]
    if not selected:
        raise RuntimeError(f"table {source_table_name} has no expected columns for {target_name}")
    return f"SELECT {', '.join(selected)} FROM {source_table_name}"


def _normalize_outbound_scans(df: pd.DataFrame) -> pd.DataFrame:
    if "operator_id" in df.columns:
        df["operator_role"] = df["operator_id"].map(map_operator_to_role)
        df = df.drop(columns=["operator_id"])
    if "voided_by" in df.columns:
        df["voided_by_role"] = df["voided_by"].map(map_operator_to_role)
        df = df.drop(columns=["voided_by"])
    return df


def _normalize_inventory_movements(df: pd.DataFrame) -> pd.DataFrame:
    if "operator_id" in df.columns:
        df["operator_role"] = df["operator_id"].map(map_operator_to_role)
        df = df.drop(columns=["operator_id"])
    return df


def _normalize_progress_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    if "operator_id" in df.columns:
        df["operator_role"] = df["operator_id"].map(map_operator_to_role)
        df = df.drop(columns=["operator_id"])
    if "detail_json" in df.columns:
        df["detail_json"] = df["detail_json"].map(redact_detail_json)
    return df


def _normalize_records(df: pd.DataFrame) -> pd.DataFrame:
    if "operator_id" in df.columns:
        df["operator_role"] = df["operator_id"].map(map_operator_to_role)
        df = df.drop(columns=["operator_id"])
    return df


def _normalize_table(table: str, df: pd.DataFrame) -> pd.DataFrame:
    if table == "outbound_scans":
        return _normalize_outbound_scans(df)
    if table == "inventory_movements":
        return _normalize_inventory_movements(df)
    if table == "progress_snapshots":
        return _normalize_progress_snapshots(df)
    if table == "records":
        return _normalize_records(df)
    return df


def _get_git_commit() -> str:
    try:
        value = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
    return value or "unknown"


def _dtype_map(df: pd.DataFrame) -> dict[str, str]:
    return {column: str(dtype) for column, dtype in df.dtypes.items()}


def run_export(*, output_dir: Path, snapshot_date: date, database_url: str) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url)
    table_specs = {
        "outbound_scans": ("outbound_scans", _table_columns()["outbound_scans"]),
        "inventory_movements": ("inventory_movements", _table_columns()["inventory_movements"]),
        "progress_snapshots": (
            "outbound_progress_snapshots",
            _table_columns()["progress_snapshots"],
        ),
        "records": ("records", _table_columns()["records"]),
    }
    generated_at = datetime.now(UTC).isoformat()
    manifest_tables: dict[str, dict[str, object]] = {}

    with engine.connect() as conn:
        for table, (source_table_name, wanted_columns) in table_specs.items():
            present_columns = _available_columns(conn, source_table_name)
            query = _build_select(source_table_name, table, wanted_columns, present_columns)
            df = pd.read_sql(text(query), conn)
            normalized = _normalize_table(table, df)
            parquet_path = output_dir / f"{table}.parquet"
            normalized.to_parquet(parquet_path, index=False, engine="pyarrow")
            manifest_tables[table] = {
                "file": parquet_path.name,
                "row_count": int(len(normalized)),
                "schema": _dtype_map(normalized),
            }

    manifest = {
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "git_commit": _get_git_commit(),
        "database_url_scheme": database_url.split(":", 1)[0],
        "tables": manifest_tables,
    }
    manifest_path = output_dir / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    args = _parse_args()
    snapshot_date = _resolve_snapshot_date(args.snapshot_date)
    output_dir = Path(args.output_dir).expanduser().resolve()
    database_url = args.database_url.strip() or _load_default_database_url()
    manifest = run_export(
        output_dir=output_dir,
        snapshot_date=snapshot_date,
        database_url=database_url,
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
