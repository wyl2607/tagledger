from backend.app.config import get_settings
from backend.app.ocr.barcode_provider import BarcodeProvider
from backend.app.ocr.base import OCRProvider
from backend.app.ocr.mock_provider import MockOCRProvider
from backend.app.ocr.tesseract_provider import TesseractOCRProvider


def get_ocr_provider() -> OCRProvider:
    provider_name = get_settings().ocr_provider.strip().lower()
    if provider_name == "tesseract":
        return TesseractOCRProvider()
    return MockOCRProvider()


def get_mock_ocr_provider() -> OCRProvider:
    return MockOCRProvider()


def get_barcode_provider() -> BarcodeProvider | None:
    if not get_settings().enable_barcode:
        return None
    try:
        return BarcodeProvider()
    except RuntimeError:
        return None
