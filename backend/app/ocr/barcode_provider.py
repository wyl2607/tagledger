from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised only in missing dependency envs
    Image = None  # type: ignore[assignment]

try:
    from pyzbar.pyzbar import decode
except ImportError as exc:  # pragma: no cover - exercised only in missing dependency envs
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
        if decode is None:
            raise RuntimeError(
                "pyzbar is required for barcode detection. On macOS run "
                "`brew install zbar` and `pip install pyzbar`; on Windows run "
                "`pip install pyzbar` (zbar is bundled)."
            ) from _PYZBAR_IMPORT_ERROR
        if Image is None:
            raise RuntimeError(
                "Pillow is required for barcode detection. Install with "
                '`pip install -e ".[barcode]"`.'
            )

    def detect(self, image_path: Path) -> list[BarcodeResult]:
        with Image.open(image_path) as image:  # type: ignore[union-attr]
            symbols = decode(image)  # type: ignore[misc]

        return [self._to_result(symbol) for symbol in symbols]

    @staticmethod
    def _to_result(symbol: Any) -> BarcodeResult:
        rect = getattr(symbol, "rect", None)
        bbox = (rect.left, rect.top, rect.width, rect.height) if rect is not None else None
        return BarcodeResult(
            type=symbol.type,
            data=symbol.data.decode("utf-8"),
            bbox=bbox,
        )
