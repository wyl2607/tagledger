import json
from pathlib import Path

from sqlmodel import Session

from backend.app.database import engine
from backend.app.models import Record, RecordStatus, utc_now
from backend.app.ocr.base import OCRResult
from backend.app.ocr.factory import (
    get_barcode_provider,
    get_mock_ocr_provider,
    get_ocr_provider,
)
from backend.app.ocr.parser import parse_label_text
from backend.app.services.dedup import find_duplicates
from backend.app.services.material_mapping import find_material_matches, material_matches_to_text

TESSERACT_UNAVAILABLE_MESSAGE = "Tesseract 未安装，已跳过 OCR，仅条码可用"


def process_record_ocr(session: Session, record: Record) -> None:
    image_path = Path(record.image_path)
    barcode_results = []
    barcode_provider = get_barcode_provider()
    barcode_available = barcode_provider is not None
    if barcode_provider is not None:
        try:
            barcode_results = barcode_provider.detect(image_path)
        except Exception:
            barcode_results = []

    barcode_payload = [{"type": barcode.type, "data": barcode.data} for barcode in barcode_results]
    barcode_lines = "".join(f"BARCODE: {barcode['data']}\n" for barcode in barcode_payload)

    provider = get_ocr_provider()
    last_error = None
    needs_review = False
    try:
        result = provider.extract_text(image_path)
    except RuntimeError:
        if barcode_available:
            result = OCRResult(text="", confidence=0.0)
            last_error = TESSERACT_UNAVAILABLE_MESSAGE
            needs_review = True
        else:
            fallback = get_mock_ocr_provider()
            result = fallback.extract_text(image_path)

    merged_text = barcode_lines + result.text
    parsed = parse_label_text(merged_text)
    material_matches = find_material_matches(merged_text)
    next_vin_or_bin = parsed.vin_or_bin
    next_serial_number = parsed.serial_number
    if material_matches:
        match = material_matches[0]
        next_vin_or_bin = match.ruiyun_part_number
        next_serial_number = match.sku
    duplicates = find_duplicates(
        session,
        vin_or_bin=next_vin_or_bin,
        serial_number=next_serial_number,
        exclude_id=record.id,
    )
    match_text = material_matches_to_text(material_matches)
    record.raw_ocr_text = f"{merged_text}\n\n{match_text}" if match_text else merged_text
    record.barcodes_json = json.dumps(barcode_payload, ensure_ascii=False)
    record.confidence_score = result.confidence
    record.model = parsed.model
    record.vin_or_bin = next_vin_or_bin
    record.serial_number = next_serial_number
    if duplicates:
        record.status = RecordStatus.duplicate
    elif needs_review:
        record.status = RecordStatus.needs_review
    else:
        record.status = RecordStatus.ocr_done
    record.last_error = last_error
    record.updated_at = utc_now()
    session.add(record)
    session.commit()


def run_ocr(record_id: int) -> None:
    with Session(engine) as session:
        record = session.get(Record, record_id)
        if record is None:
            return
        process_record_ocr(session, record)


run_mock_ocr = run_ocr
