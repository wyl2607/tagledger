from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class Category(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class RecordStatus(StrEnum):
    uploaded = "uploaded"
    ocr_done = "ocr_done"
    needs_review = "needs_review"
    confirmed = "confirmed"
    submitted = "submitted"
    submission_failed = "submission_failed"
    duplicate = "duplicate"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Record(SQLModel, table=True):
    __tablename__ = "records"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    image_path: str
    category: Category
    model: str | None = Field(default=None, index=True)
    vin_or_bin: str | None = Field(default=None, index=True)
    serial_number: str | None = Field(default=None, index=True)
    operator_id: str = Field(default="self", index=True)
    raw_ocr_text: str | None = None
    barcodes_json: str | None = None
    confidence_score: float | None = None
    status: RecordStatus = Field(default=RecordStatus.uploaded, index=True)
    submission_attempts: int = 0
    last_error: str | None = None
    error_screenshot: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None


class OutboundScan(SQLModel, table=True):
    __tablename__ = "outbound_scans"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    order_no: str = Field(index=True)
    part_code: str = Field(index=True)
    location_code: str | None = Field(default=None, index=True)
    source_code: str
    matched_code: str
    quantity: int = Field(default=1)
    status: str = Field(default="active", index=True)
    operator_id: str = Field(default="self", index=True)
    batch_id: str | None = Field(default=None, index=True)
    record_id: int | None = Field(default=None, index=True)
    verification_record_id: int | None = Field(default=None, index=True)
    void_reason: str | None = None
    voided_by: str | None = Field(default=None, index=True)
    voided_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class OutboundProgressSnapshot(SQLModel, table=True):
    __tablename__ = "outbound_progress_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    order_no: str = Field(index=True)
    event: str = Field(index=True)
    required_total: int
    scanned_total: int
    remaining_total: int
    line_total: int
    complete_line_total: int
    active_scan_count: int
    active_scan_quantity: int
    operator_id: str = Field(default="self", index=True)
    batch_id: str | None = Field(default=None, index=True)
    scan_id: int | None = Field(default=None, index=True)
    completed_at: datetime | None = Field(default=None, index=True)
    detail_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class InventoryLocation(SQLModel, table=True):
    __tablename__ = "inventory_locations"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    part_key: str = Field(index=True)
    part_name: str | None = Field(default=None)
    location_code: str = Field(index=True)
    quantity: int = Field(default=0)
    status: str = Field(default="active", index=True)
    zero_stock: bool = Field(default=True, index=True)
    location_kind: str = Field(default="permanent")
    replacement_location_code: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class InventoryMovement(SQLModel, table=True):
    __tablename__ = "inventory_movements"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    movement_type: str = Field(index=True)
    part_key: str = Field(index=True)
    location_code: str = Field(index=True)
    order_no: str | None = Field(default=None, index=True)
    scan_id: int | None = Field(default=None, index=True)
    quantity_delta: int
    before_qty: int
    after_qty: int
    operator_id: str = Field(default="self", index=True)
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    username: str = Field(index=True, unique=True)
    display_name: str
    password_hash: str
    role: str = Field(default="operator", index=True)
    status: str = Field(default="active", index=True)
    outbound_last_order_no: str | None = Field(default=None, index=True)
    must_change_password: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_login_at: datetime | None = None


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"

    id: int | None = Field(default=None, primary_key=True)
    session_token_hash: str = Field(index=True, unique=True)
    user_id: int = Field(index=True)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    factory_id: str = Field(default="factory_a", index=True)
    event_type: str = Field(index=True)
    actor_user_id: int | None = Field(default=None, index=True)
    actor_username: str | None = Field(default=None, index=True)
    target_type: str | None = Field(default=None, index=True)
    target_id: str | None = Field(default=None, index=True)
    action: str
    reason: str | None = None
    success: bool = Field(default=True, index=True)
    detail_json: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SecuritySecret(SQLModel, table=True):
    __tablename__ = "security_secrets"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    secret_hash: str
    updated_by_user_id: int | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
