import subprocess

import pytest

pytesseract = pytest.importorskip("pytesseract")
Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
ImageFont = pytest.importorskip("PIL.ImageFont")


def test_tesseract_provider_extracts_mammotion_fields(tmp_path) -> None:
    try:
        subprocess.run(
            ["tesseract", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("tesseract executable is not available")

    from backend.app.ocr.parser import parse_label_text
    from backend.app.ocr.tesseract_provider import TesseractOCRProvider

    lines = [
        "Product Name: YUKA mini",
        "Model: 500",
        "Net Weight: 14.5 kg",
        "Gross Weight: 17.8 kg",
        "SKU: MTL24YUM1EU01-A",
        "Package Size: 660(L)*470(W)*375(H)mm",
        "Device Name: Yuka-MN35EUF7",
        "SN  YK2TEU251657627",
    ]
    image_path = tmp_path / "mammotion-label.png"
    image = Image.new("RGB", (1200, 420), "white")
    draw = ImageDraw.Draw(image)
    font = _load_test_font(size=28)

    for index, line in enumerate(lines):
        draw.text((32, 24 + index * 46), line, fill="black", font=font)
    image.save(image_path)

    result = TesseractOCRProvider().extract_text(image_path)
    parsed = parse_label_text(result.text)

    assert parsed.model is not None
    assert "500" in parsed.model
    assert parsed.vin_or_bin == "MTL24YUM1EU01-A"
    assert parsed.serial_number == "YK2TEU251657627"


def _load_test_font(size: int):
    for font_path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
