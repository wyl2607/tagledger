from datetime import datetime

from pydantic import BaseModel, field_validator

from backend.app.models import Category, RecordStatus


class DuplicateRecord(BaseModel):
    id: int
    model: str | None
    vin_or_bin: str | None
    serial_number: str | None
    status: RecordStatus


class BarcodeRead(BaseModel):
    type: str
    data: str


class RecordRead(BaseModel):
    id: int
    image_path: str
    category: Category
    model: str | None
    vin_or_bin: str | None
    serial_number: str | None
    raw_ocr_text: str | None
    confidence_score: float | None
    status: RecordStatus
    last_error: str | None
    barcodes: list[BarcodeRead] = []
    created_at: datetime
    updated_at: datetime
    duplicates: list[DuplicateRecord] = []


class RecordListItem(BaseModel):
    id: int
    image_path: str
    category: Category
    model: str | None
    vin_or_bin: str | None
    serial_number: str | None
    confidence_score: float | None
    status: RecordStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    job_id: int
    status: RecordStatus
    barcodes: list[BarcodeRead] = []
    duplicates: list[DuplicateRecord] = []


class BatchUploadJob(BaseModel):
    job_id: int
    filename: str
    status: RecordStatus
    barcodes: list[BarcodeRead] = []
    duplicates: list[DuplicateRecord] = []


class BatchUploadResponse(BaseModel):
    jobs: list[BatchUploadJob]


class ConfirmRequest(BaseModel):
    category: Category | None = None
    model: str | None = None
    vin_or_bin: str | None = None
    serial_number: str | None = None
    duplicate_action: str = "abandon"

    @field_validator("model", "vin_or_bin", "serial_number")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @field_validator("duplicate_action")
    @classmethod
    def validate_duplicate_action(cls, value: str) -> str:
        if value not in {"abandon", "overwrite"}:
            raise ValueError("duplicate_action must be abandon or overwrite")
        return value


class ConfirmResponse(BaseModel):
    id: int
    status: RecordStatus
    duplicates: list[DuplicateRecord] = []


class RetryResponse(BaseModel):
    id: int
    status: RecordStatus
