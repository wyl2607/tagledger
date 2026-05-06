#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, select, text

TABLES = [
    "records",
    "outbound_scans",
    "outbound_progress_snapshots",
    "inventory_locations",
    "inventory_movements",
    "users",
    "user_sessions",
    "audit_logs",
    "security_secrets",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-shot ETL from SQLite to Postgres.")
    parser.add_argument("--sqlite-url", required=True, help="e.g. sqlite:////abs/path/to/app.db")
    parser.add_argument(
        "--postgres-url", required=True, help="e.g. postgresql://user:pass@host:5432/db"
    )
    parser.add_argument(
        "--factory-id",
        default="factory_a",
        choices=["factory_a", "factory_b", "factory_c"],
        help="default factory_id backfill value when source row is null/empty",
    )
    parser.add_argument(
        "--report-json",
        default="",
        help="optional path to write row-count report JSON",
    )
    return parser.parse_args()


def _normalize_postgres_url(url: str) -> str:
    raw_url = url.strip()
    for prefix in ("postgresql://", "postgres://"):
        if raw_url.startswith(prefix):
            return raw_url.replace(prefix, "postgresql+psycopg://", 1)
    return raw_url


def _normalize_factory_id(row: dict[str, Any], default_factory_id: str) -> dict[str, Any]:
    if "factory_id" in row and (row["factory_id"] is None or str(row["factory_id"]).strip() == ""):
        row["factory_id"] = default_factory_id
    return row


def _row_count(connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _is_postgres_url(url: str) -> bool:
    return _normalize_postgres_url(url).startswith("postgresql+psycopg://")


def _reset_postgres_sequence(connection, table_name: str, column_name: str = "id") -> bool:
    sequence_name = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    if not sequence_name:
        return False
    connection.execute(
        text(
            "SELECT setval("
            "CAST(:sequence_name AS regclass), "
            f"COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1), "
            f"(SELECT MAX({column_name}) IS NOT NULL FROM {table_name})"
            ")"
        ),
        {"sequence_name": sequence_name},
    )
    return True


def _post_commit_counts(engine, metadata: MetaData) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table_name in TABLES:
            counts[table_name] = _row_count(connection, metadata.tables[table_name])
    return counts


def run_etl(
    sqlite_url: str, postgres_url: str, default_factory_id: str
) -> dict[str, dict[str, int]]:
    sqlite_engine = create_engine(sqlite_url)
    normalized_postgres_url = _normalize_postgres_url(postgres_url)
    postgres_engine = create_engine(normalized_postgres_url)

    sqlite_metadata = MetaData()
    postgres_metadata = MetaData()
    sqlite_metadata.reflect(bind=sqlite_engine, only=TABLES)
    postgres_metadata.reflect(bind=postgres_engine, only=TABLES)

    missing_sqlite = [name for name in TABLES if name not in sqlite_metadata.tables]
    missing_pg = [name for name in TABLES if name not in postgres_metadata.tables]
    if missing_sqlite:
        raise RuntimeError(f"SQLite missing tables: {', '.join(missing_sqlite)}")
    if missing_pg:
        raise RuntimeError(f"Postgres missing tables: {', '.join(missing_pg)}")

    report: dict[str, dict[str, int]] = {}

    with sqlite_engine.connect() as src_conn, postgres_engine.begin() as dst_conn:
        for table_name in TABLES:
            src_table = sqlite_metadata.tables[table_name]
            dst_table = postgres_metadata.tables[table_name]

            dst_count = _row_count(dst_conn, dst_table)
            if dst_count > 0:
                raise RuntimeError(
                    f"Postgres target table '{table_name}' is not empty ({dst_count} rows); aborting."
                )

            src_rows = src_conn.execute(select(src_table)).mappings().all()
            prepared_rows = [
                _normalize_factory_id(dict(row), default_factory_id) for row in src_rows
            ]
            if prepared_rows:
                dst_conn.execute(dst_table.insert(), prepared_rows)
            copied_count = len(prepared_rows)
            transaction_count = _row_count(dst_conn, dst_table)
            if transaction_count != copied_count:
                raise RuntimeError(
                    f"Row count mismatch for {table_name}: "
                    f"copied={copied_count}, transaction={transaction_count}"
                )
            sequence_reset = False
            if _is_postgres_url(normalized_postgres_url) and "id" in dst_table.columns:
                sequence_reset = _reset_postgres_sequence(dst_conn, table_name)
            report[table_name] = {
                "source": len(src_rows),
                "copied": copied_count,
                "target": transaction_count,
                "post_commit_target": -1,
                "sequence_reset": int(sequence_reset),
            }

    post_commit_counts = _post_commit_counts(postgres_engine, postgres_metadata)
    for table_name, post_commit_count in post_commit_counts.items():
        copied_count = report[table_name]["copied"]
        if post_commit_count != copied_count:
            raise RuntimeError(
                f"Post-commit row count mismatch for {table_name}: "
                f"copied={copied_count}, post_commit={post_commit_count}"
            )
        report[table_name]["post_commit_target"] = post_commit_count

    return report


def main() -> int:
    args = _parse_args()
    report = run_etl(args.sqlite_url, args.postgres_url, args.factory_id)
    output = {
        "sqlite_url": args.sqlite_url,
        "postgres_url": args.postgres_url,
        "factory_id": args.factory_id,
        "tables": report,
    }
    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
