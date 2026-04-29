from backend.app.ocr.parser import parse_label_text

MAMMOTION_LABEL_TEXT = """
Product Name: YUKA mini
Model: 500
Net Weight: 14.5 kg
Gross Weight: 17.8 kg
SKU: MTL24YUM1EU01-A
Package Size: 660(L)*470(W)*375(H)mm
Device Name: Yuka-MN35EUF7
SN  YK2TEU251657627
"""


def test_parse_label_text_extracts_common_fields() -> None:
    parsed = parse_label_text(
        """
        MODEL: ZX-200
        VIN/BIN Number: ab12cd3456
        SN: sn-998877
        """
    )

    assert parsed.model == "ZX-200"
    assert parsed.vin_or_bin == "AB12CD3456"
    assert parsed.serial_number == "SN-998877"


def test_parse_label_text_accepts_serial_number_label() -> None:
    parsed = parse_label_text("Model # M450\nBIN NO. BIN777888\nSerial Number: s12345")

    assert parsed.model == "M450"
    assert parsed.vin_or_bin == "BIN777888"
    assert parsed.serial_number == "S12345"


def test_parse_label_text_returns_none_for_missing_fields() -> None:
    parsed = parse_label_text("unstructured blurry text")

    assert parsed.model is None
    assert parsed.vin_or_bin is None
    assert parsed.serial_number is None


def test_parser_handles_sku_as_vin_or_bin() -> None:
    parsed = parse_label_text("SKU: MTL24YUM1EU01-A")

    assert parsed.vin_or_bin == "MTL24YUM1EU01-A"


def test_parser_handles_sn_without_colon() -> None:
    parsed = parse_label_text("SN  YK2TEU251657627")

    assert parsed.serial_number == "YK2TEU251657627"


def test_parser_handles_full_mammotion_label() -> None:
    parsed = parse_label_text(MAMMOTION_LABEL_TEXT)

    assert parsed.model == "500"
    assert parsed.vin_or_bin == "MTL24YUM1EU01-A"
    assert parsed.serial_number == "YK2TEU251657627"
