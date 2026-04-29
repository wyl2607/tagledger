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
