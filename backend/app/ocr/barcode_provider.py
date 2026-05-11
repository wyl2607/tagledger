from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised only in missing dependency envs
    Image = None  # type: ignore[assignment]

try:
    import cv2
except ImportError:  # pragma: no cover - exercised only in missing dependency envs
    cv2 = None  # type: ignore[assignment]

try:
    from pyzbar.pyzbar import decode
except Exception as exc:  # pragma: no cover - import may fail on missing native DLLs
    decode = None  # type: ignore[assignment]
    _PYZBAR_IMPORT_ERROR = exc
else:
    _PYZBAR_IMPORT_ERROR = None


@dataclass(frozen=True)
class BarcodeResult:
    type: str
    data: str
    bbox: tuple[int, int, int, int] | None


class BarcodeProvider:
    def __init__(self) -> None:
        if decode is None and cv2 is None:
            raise RuntimeError(
                "Barcode/QR detection requires pyzbar or OpenCV. "
                'Install with `pip install -e ".[barcode,ocr]"`.'
            ) from _PYZBAR_IMPORT_ERROR
        if Image is None:
            raise RuntimeError(
                "Pillow is required for barcode detection. Install with "
                '`pip install -e ".[barcode]"`.'
            )

    def detect(self, image_path: Path) -> list[BarcodeResult]:
        if decode is not None:
            with Image.open(image_path) as image:  # type: ignore[union-attr]
                symbols = decode(image)  # type: ignore[misc]
            return [self._to_result(symbol) for symbol in symbols]
        return self._detect_with_cv2(image_path)

    @staticmethod
    def _to_result(symbol: Any) -> BarcodeResult:
        rect = getattr(symbol, "rect", None)
        bbox = (rect.left, rect.top, rect.width, rect.height) if rect is not None else None
        return BarcodeResult(
            type=symbol.type,
            data=symbol.data.decode("utf-8"),
            bbox=bbox,
        )

    @staticmethod
    def _detect_with_cv2(image_path: Path) -> list[BarcodeResult]:
        if cv2 is None:
            return []
        image = cv2.imread(str(image_path))
        if image is None:
            return []
        detector = cv2.QRCodeDetector()

        results: list[BarcodeResult] = []
        has_multi, decoded_multi, points_multi, _ = detector.detectAndDecodeMulti(image)
        if has_multi and decoded_multi is not None:
            for index, text in enumerate(decoded_multi):
                if not text:
                    continue
                bbox = None
                if points_multi is not None and index < len(points_multi):
                    pts = points_multi[index]
                    xs = [int(p[0]) for p in pts]
                    ys = [int(p[1]) for p in pts]
                    bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                results.append(BarcodeResult(type="QRCODE", data=text, bbox=bbox))
        if results:
            return results

        text_single, points_single, _ = detector.detectAndDecode(image)
        if not text_single:
            return []
        bbox_single = None
        if points_single is not None:
            pts = points_single
            xs = [int(p[0]) for p in pts]
            ys = [int(p[1]) for p in pts]
            bbox_single = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return [BarcodeResult(type="QRCODE", data=text_single, bbox=bbox_single)]
