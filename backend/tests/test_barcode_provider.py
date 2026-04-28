from pathlib import Path

import pytest


def _optional_module(name: str):
    try:
        return pytest.importorskip(name)
    except pytest.skip.Exception:
        return None


pyzbar = _optional_module("pyzbar.pyzbar")
Image = _optional_module("PIL.Image")
ImageDraw = _optional_module("PIL.ImageDraw")
barcode = _optional_module("barcode")
barcode_writer = _optional_module("barcode.writer")
qrcode = _optional_module("qrcode")


def test_detect_reads_multiple_codes_from_one_image(tmp_path: Path) -> None:
    if None in (pyzbar, Image, ImageDraw, barcode, barcode_writer, qrcode):
        pytest.skip("optional barcode detection or generation dependencies are not installed")

    from backend.app.ocr.barcode_provider import BarcodeProvider

    expected_ean = "6976152583088"
    expected_qr = "MTL24YUM1EU01-A"
    image_path = tmp_path / "multi-code-label.png"

    ean_class = barcode.get_barcode_class("ean13")
    ean_image = ean_class(expected_ean, writer=barcode_writer.ImageWriter()).render(
        writer_options={"write_text": False, "module_height": 18.0}
    )
    qr_image = qrcode.make(expected_qr).convert("RGB")

    canvas = Image.new("RGB", (900, 360), "white")
    canvas.paste(ean_image.convert("RGB"), (40, 40))
    canvas.paste(qr_image.resize((220, 220)), (600, 60))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 300), "EAN-13 + QR test label", fill="black")
    canvas.save(image_path)

    results = BarcodeProvider().detect(image_path)
    data = {result.data for result in results}

    assert expected_ean in data
    assert expected_qr in data
