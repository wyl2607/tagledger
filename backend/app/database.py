from collections.abc import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from backend.app.config import get_settings

settings = get_settings()
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
database_url = f"sqlite:///{settings.database_path.as_posix()}"

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(records)")).fetchall()}
        if "barcodes_json" not in columns:
            conn.execute(text("ALTER TABLE records ADD COLUMN barcodes_json TEXT"))
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
        signoff_pairing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(signoff_pairing_keys)")).fetchall()
        }
        if signoff_pairing_columns:
            if "preview_count" not in signoff_pairing_columns:
                conn.execute(
                    text(
                        "ALTER TABLE signoff_pairing_keys ADD COLUMN preview_count INTEGER DEFAULT 0"
                    )
                )
            if "last_previewed_at" not in signoff_pairing_columns:
                conn.execute(
                    text("ALTER TABLE signoff_pairing_keys ADD COLUMN last_previewed_at DATETIME")
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_signoff_pairing_keys_last_previewed_at "
                    "ON signoff_pairing_keys(last_previewed_at)"
                )
            )
        inventory_movement_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(inventory_movements)")).fetchall()
        }
        if inventory_movement_columns:
            if "idempotency_key" not in inventory_movement_columns:
                conn.execute(
                    text("ALTER TABLE inventory_movements ADD COLUMN idempotency_key TEXT")
                )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_movements_inbound_idempotency "
                    "ON inventory_movements(movement_type, operator_id, idempotency_key) "
                    "WHERE idempotency_key IS NOT NULL"
                )
            )


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
