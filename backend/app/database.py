import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from backend.app.config import get_settings, normalize_database_url

settings = get_settings()


def _resolve_database_url() -> str:
    override_url = (os.getenv("DATABASE_URL") or "").strip()
    if override_url:
        return normalize_database_url(override_url)
    override_path = (os.getenv("DATABASE_PATH") or "").strip()
    if override_path:
        resolved = Path(override_path).expanduser().resolve()
        return f"sqlite:///{resolved.as_posix()}"
    return normalize_database_url(settings.resolved_database_url)


def _ensure_sqlite_parent(url: str) -> None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return
    raw_path = url.removeprefix(prefix)
    if raw_path in {"", ":memory:"}:
        return
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[2] / candidate
    candidate.parent.mkdir(parents=True, exist_ok=True)


def _alembic_head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def _ensure_postgres_schema_current() -> None:
    expected_revision = _alembic_head_revision()
    with engine.connect() as conn:
        has_alembic_version = conn.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'alembic_version'"
                ")"
            )
        ).scalar_one()
        if not has_alembic_version:
            raise RuntimeError(
                "Postgres schema is not managed by Alembic yet. "
                "Run with RUN_MIGRATIONS=1 or execute alembic upgrade head before startup."
            )
        current_revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        if current_revision != expected_revision:
            raise RuntimeError(
                "Postgres schema is not at Alembic head. "
                f"Current revision: {current_revision}; expected: {expected_revision}. "
                "Run with RUN_MIGRATIONS=1 or execute alembic upgrade head before startup."
            )


database_url = _resolve_database_url()
_ensure_sqlite_parent(database_url)

engine_connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(
    database_url,
    connect_args=engine_connect_args,
)


def create_db_and_tables() -> None:
    if os.getenv("RUN_MIGRATIONS") == "1":
        from alembic import command
        from alembic.config import Config

        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", _resolve_database_url())
        command.upgrade(config, "head")
        return

    if not database_url.startswith("sqlite"):
        _ensure_postgres_schema_current()
        return

    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(records)")).fetchall()}
        if "barcodes_json" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN barcodes_json TEXT"))
        if "factory_id" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN factory_id TEXT DEFAULT 'factory_a'"))
        if "submission_attempts" not in columns:
            conn.execute(
                text("ALTER TABLE records ADD COLUMN submission_attempts INTEGER DEFAULT 0")
            )
        if "error_screenshot" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN error_screenshot TEXT"))
        if "submitted_at" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN submitted_at DATETIME"))
        if "operator_id" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN operator_id TEXT DEFAULT 'self'"))
        conn.execute(
            text(
                "UPDATE records SET operator_id = 'self' WHERE operator_id IS NULL OR operator_id = ''"
            )
        )
        conn.execute(
            text(
                "UPDATE records "
                "SET factory_id = 'factory_a' "
                "WHERE factory_id IS NULL OR factory_id = ''"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_records_vin_or_bin "
                "ON records(vin_or_bin) "
                "WHERE vin_or_bin IS NOT NULL AND status != 'duplicate'"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_records_serial_number "
                "ON records(serial_number) "
                "WHERE serial_number IS NOT NULL AND status != 'duplicate'"
            )
        )
        scan_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(outbound_scans)")).fetchall()
        }
        if scan_columns:
            if "source_code" not in scan_columns:
                conn.execute(
                    text("ALTER TABLE outbound_scans ADD COLUMN source_code TEXT DEFAULT ''")
                )
            if "factory_id" not in scan_columns:
                conn.execute(
                    text(
                        "ALTER TABLE outbound_scans ADD COLUMN factory_id TEXT DEFAULT 'factory_a'"
                    )
                )
            if "matched_code" not in scan_columns:
                conn.execute(
                    text("ALTER TABLE outbound_scans ADD COLUMN matched_code TEXT DEFAULT ''")
                )
            if "location_code" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN location_code TEXT"))
            if "operator_id" not in scan_columns:
                conn.execute(
                    text("ALTER TABLE outbound_scans ADD COLUMN operator_id TEXT DEFAULT 'self'")
                )
            if "batch_id" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN batch_id TEXT"))
            if "record_id" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN record_id INTEGER"))
            if "created_at" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN created_at DATETIME"))
            if "quantity" not in scan_columns:
                conn.execute(
                    text("ALTER TABLE outbound_scans ADD COLUMN quantity INTEGER DEFAULT 1")
                )
            if "status" not in scan_columns:
                conn.execute(
                    text("ALTER TABLE outbound_scans ADD COLUMN status TEXT DEFAULT 'active'")
                )
            if "void_reason" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN void_reason TEXT"))
            if "voided_by" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN voided_by TEXT"))
            if "voided_at" not in scan_columns:
                conn.execute(text("ALTER TABLE outbound_scans ADD COLUMN voided_at DATETIME"))
            conn.execute(
                text(
                    "UPDATE outbound_scans SET quantity = 1 WHERE quantity IS NULL OR quantity < 1"
                )
            )
            conn.execute(
                text(
                    "UPDATE outbound_scans SET status = 'active' "
                    "WHERE status IS NULL OR status = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE outbound_scans "
                    "SET factory_id = 'factory_a' "
                    "WHERE factory_id IS NULL OR factory_id = ''"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_outbound_scans_record "
                    "ON outbound_scans(order_no, part_code, record_id) "
                    "WHERE record_id IS NOT NULL AND status = 'active'"
                )
            )
        snapshot_columns = {
            row[1]
            for row in conn.execute(
                text("PRAGMA table_info(outbound_progress_snapshots)")
            ).fetchall()
        }
        if snapshot_columns:
            for column, definition in {
                "factory_id": "TEXT DEFAULT 'factory_a'",
                "order_no": "TEXT DEFAULT ''",
                "event": "TEXT DEFAULT ''",
                "required_total": "INTEGER DEFAULT 0",
                "scanned_total": "INTEGER DEFAULT 0",
                "remaining_total": "INTEGER DEFAULT 0",
                "line_total": "INTEGER DEFAULT 0",
                "complete_line_total": "INTEGER DEFAULT 0",
                "active_scan_count": "INTEGER DEFAULT 0",
                "active_scan_quantity": "INTEGER DEFAULT 0",
                "operator_id": "TEXT DEFAULT 'self'",
                "batch_id": "TEXT",
                "scan_id": "INTEGER",
                "detail_json": "TEXT",
                "created_at": "DATETIME",
            }.items():
                if column not in snapshot_columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE outbound_progress_snapshots ADD COLUMN {column} {definition}"
                        )
                    )
            conn.execute(
                text(
                    "UPDATE outbound_progress_snapshots "
                    "SET factory_id = 'factory_a' "
                    "WHERE factory_id IS NULL OR factory_id = ''"
                )
            )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username)"))
        user_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
        if "outbound_last_order_no" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN outbound_last_order_no TEXT"))
        if "factory_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN factory_id TEXT DEFAULT 'factory_a'"))
        conn.execute(
            text(
                "UPDATE users SET factory_id = 'factory_a' WHERE factory_id IS NULL OR factory_id = ''"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_sessions_token "
                "ON user_sessions(session_token_hash)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_security_secrets_key ON security_secrets(key)"
            )
        )
        inventory_location_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(inventory_locations)")).fetchall()
        }
        if inventory_location_columns:
            for column, definition in {
                "factory_id": "TEXT DEFAULT 'factory_a'",
                "part_key": "TEXT DEFAULT ''",
                "part_name": "TEXT",
                "location_code": "TEXT DEFAULT ''",
                "quantity": "INTEGER DEFAULT 0",
                "status": "TEXT DEFAULT 'active'",
                "zero_stock": "INTEGER DEFAULT 1",
                "location_kind": "TEXT DEFAULT 'permanent'",
                "replacement_location_code": "TEXT",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            }.items():
                if column not in inventory_location_columns:
                    conn.execute(
                        text(f"ALTER TABLE inventory_locations ADD COLUMN {column} {definition}")
                    )
            conn.execute(
                text(
                    "UPDATE inventory_locations "
                    "SET status = 'active' WHERE status IS NULL OR status = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE inventory_locations "
                    "SET zero_stock = CASE WHEN quantity <= 0 THEN 1 ELSE 0 END"
                )
            )
            conn.execute(
                text(
                    "UPDATE inventory_locations "
                    "SET location_kind = 'permanent' "
                    "WHERE location_kind IS NULL OR location_kind = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE inventory_locations "
                    "SET factory_id = 'factory_a' "
                    "WHERE factory_id IS NULL OR factory_id = ''"
                )
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_locations_part_location "
                "ON inventory_locations(part_key, location_code)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_inventory_locations_status "
                "ON inventory_locations(status)"
            )
        )
        movement_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(inventory_movements)")).fetchall()
        }
        if movement_columns:
            for column, definition in {
                "factory_id": "TEXT DEFAULT 'factory_a'",
                "movement_type": "TEXT DEFAULT ''",
                "part_key": "TEXT DEFAULT ''",
                "location_code": "TEXT DEFAULT ''",
                "order_no": "TEXT",
                "scan_id": "INTEGER",
                "quantity_delta": "INTEGER DEFAULT 0",
                "before_qty": "INTEGER DEFAULT 0",
                "after_qty": "INTEGER DEFAULT 0",
                "operator_id": "TEXT DEFAULT 'self'",
                "reason": "TEXT",
                "created_at": "DATETIME",
            }.items():
                if column not in movement_columns:
                    conn.execute(
                        text(f"ALTER TABLE inventory_movements ADD COLUMN {column} {definition}")
                    )
            conn.execute(
                text(
                    "UPDATE inventory_movements "
                    "SET factory_id = 'factory_a' "
                    "WHERE factory_id IS NULL OR factory_id = ''"
                )
            )
        audit_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(audit_logs)")).fetchall()
        }
        if audit_columns:
            if "factory_id" not in audit_columns:
                conn.execute(
                    text("ALTER TABLE audit_logs ADD COLUMN factory_id TEXT DEFAULT 'factory_a'")
                )
            conn.execute(
                text(
                    "UPDATE audit_logs "
                    "SET factory_id = 'factory_a' "
                    "WHERE factory_id IS NULL OR factory_id = ''"
                )
            )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_inventory_movements_part_created "
                "ON inventory_movements(part_key, created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_inventory_movements_order "
                "ON inventory_movements(order_no)"
            )
        )


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
