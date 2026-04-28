from pathlib import Path

from backend.app.ocr.base import OCRProvider, OCRResult
from backend.app.ocr.preprocessor import preprocess_image

try:
    import pytesseract
    from pytesseract import Output
except ImportError:
    pytesseract = None
    Output = None


class TesseractOCRProvider(OCRProvider):
    def extract_text(self, image_path: Path) -> OCRResult:
        if pytesseract is None or Output is None:
            raise RuntimeError(
                "pytesseract is required for Tesseract OCR. On macOS run "
                "`brew install tesseract`; on Windows download Tesseract from the "
                "official installer and set `pytesseract.pytesseract.tesseract_cmd` "
                "to the installed tesseract.exe path."
            )

        try:
            processed_path = preprocess_image(image_path)
            text = pytesseract.image_to_string(str(processed_path), lang="eng")
            data = pytesseract.image_to_data(
                str(processed_path),
                lang="eng",
                output_type=Output.DICT,
            )
            confidences = _valid_confidences(data.get("conf", []))
            confidence = (
                sum(confidences) / len(confidences) / 100
                if confidences
                else 0.0
            )
            return OCRResult(text=text, confidence=confidence)
        except Exception as exc:
            raise RuntimeError(f"Tesseract OCR failed for {image_path}") from exc


def _valid_confidences(raw_confidences: list[object]) -> list[float]:
    confidences: list[float] = []
    for raw_confidence in raw_confidences:
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence)
    return confidences
