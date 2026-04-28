from pathlib import Path

from backend.app.ocr.base import OCRProvider, OCRResult


class MockOCRProvider(OCRProvider):
    def extract_text(self, image_path: Path) -> OCRResult:
        stem = image_path.stem.upper().replace(" ", "-")[:24] or "SAMPLE"
        text = f"MODEL: MOCK-{stem}\nVIN/BIN NUMBER: VIN-{stem}\nSN: SN-{stem}"
        return OCRResult(text=text, confidence=0.99)
