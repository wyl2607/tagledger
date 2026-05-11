from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook


def write_catalog(path: Path, rows: int = 35) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["物料编码", "SKU", "BYD料号", "瑞云料号", "描述", "类型", "品名", "箱规尺寸"])
    for index in range(rows):
        sheet.append(
            [
                f"MAT-{index:03d}",
                f"SKU-{index:03d}",
                f"BYD-{index:03d}",
                f"RY-{index:03d}",
                f"描述 {index}",
                "特殊类型" if index == rows - 1 else "普通类型",
                f"品名 {index}",
                f"{index}x30x20",
            ]
        )
    workbook.save(path)


def test_material_catalog_api_returns_all_rows_by_default(
    authenticated_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "mapping.xlsx"
    write_catalog(path)

    from backend.app.services import material_mapping

    material_mapping.clear_material_mapping_cache()

    class FakeSettings:
        material_mapping_file = path

    monkeypatch.setattr(material_mapping, "get_settings", lambda: FakeSettings())

    response = authenticated_client.get("/api/materials/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 35
    assert payload["total"] == 35
    assert payload["items"][34]["material_code"] == "MAT-034"


def test_material_catalog_api_searches_all_supported_fields(
    authenticated_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "mapping.xlsx"
    write_catalog(path)

    from backend.app.services import material_mapping

    material_mapping.clear_material_mapping_cache()

    class FakeSettings:
        material_mapping_file = path

    monkeypatch.setattr(material_mapping, "get_settings", lambda: FakeSettings())

    cases = {
        "MAT-034": "material_code",
        "SKU-034": "sku",
        "BYD-034": "byd_part_number",
        "描述 34": "description",
        "特殊类型": "material_type",
        "品名 34": "product_name",
        "34x30x20": "carton_size",
    }
    for query, field in cases.items():
        response = authenticated_client.get("/api/materials/catalog", params={"q": query})
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["items"][0][field]


def test_import_material_catalog_replaces_mapping_file(
    authenticated_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "mapping.xlsx"
    upload_path = tmp_path / "upload.xlsx"
    write_catalog(upload_path, rows=2)

    from backend.app.routes import materials
    from backend.app.services import material_mapping

    material_mapping.clear_material_mapping_cache()
    monkeypatch.setattr(materials, "_material_file_path", lambda: path)

    with upload_path.open("rb") as handle:
        response = authenticated_client.post(
            "/api/materials/catalog/import",
            files={
                "file": (
                    "mapping.xlsx",
                    handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 201
    assert response.json()["count"] == 2
    assert path.exists()
