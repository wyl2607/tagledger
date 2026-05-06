from pathlib import Path

from openpyxl import Workbook

from backend.app.services.material_mapping import (
    find_material_matches,
    load_material_matches,
    normalize_material_code,
)


def write_mapping(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["瑞云料号", "SKU"])
    sheet.append(["C.G.LM.000011000", "MTL24LUM1US02"])
    sheet.append(["C.G.LD.000010000", "MTL24LUL1EU02"])
    workbook.save(path)


def test_load_material_matches_reads_ruiyun_and_sku_columns(tmp_path: Path) -> None:
    path = tmp_path / "mapping.xlsx"
    write_mapping(path)

    matches = load_material_matches(path)

    assert matches[0].ruiyun_part_number == "C.G.LM.000011000"
    assert matches[0].sku == "MTL24LUM1US02"


def test_normalize_material_code_ignores_punctuation() -> None:
    assert normalize_material_code(" C.G.LM.000011000 ") == "CGLM000011000"


def test_find_material_matches_returns_both_numbers(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "mapping.xlsx"
    write_mapping(path)

    from backend.app.services import material_mapping

    material_mapping.clear_material_mapping_cache()

    class FakeSettings:
        material_mapping_file = path

    monkeypatch.setattr(material_mapping, "get_settings", lambda: FakeSettings())

    matches = find_material_matches("OCR text SKU MTL24LUM1US02")

    assert len(matches) == 1
    assert matches[0].ruiyun_part_number == "C.G.LM.000011000"
    assert matches[0].sku == "MTL24LUM1US02"
    assert matches[0].matched_field == "sku"


def test_load_material_matches_skips_unknown_headers(tmp_path: Path) -> None:
    path = tmp_path / "mapping.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["序号", "名称"])
    sheet.append(["1", "MTL24LUM1US02"])
    workbook.save(path)

    assert load_material_matches(path) == []


def test_material_catalog_refreshes_when_file_changes(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "mapping.xlsx"
    write_mapping(path)

    from backend.app.services import material_mapping

    material_mapping.clear_material_mapping_cache()

    class FakeSettings:
        material_mapping_file = path

    monkeypatch.setattr(material_mapping, "get_settings", lambda: FakeSettings())
    assert find_material_matches("MTL24LUM1US02")[0].ruiyun_part_number == "C.G.LM.000011000"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["瑞云料号", "SKU"])
    sheet.append(["C.NEW.0001", "MTL24LUM1US02"])
    workbook.save(path)

    assert find_material_matches("MTL24LUM1US02")[0].ruiyun_part_number == "C.NEW.0001"
