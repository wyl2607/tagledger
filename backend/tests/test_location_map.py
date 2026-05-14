from sqlmodel import Session

from backend.app.models import InventoryLocation
from backend.app.services.location_map import build_inventory_location_map


def _seed_location(
    session: Session,
    *,
    part_key: str,
    location_code: str,
    quantity: int,
    part_name: str | None = None,
    location_kind: str = "permanent",
    status: str | None = None,
    factory_id: str = "factory_a",
) -> InventoryLocation:
    row = InventoryLocation(
        factory_id=factory_id,
        part_key=part_key,
        part_name=part_name,
        location_code=location_code,
        quantity=quantity,
        status=status or ("active" if quantity > 0 else "zero_stock"),
        zero_stock=quantity <= 0,
        location_kind=location_kind,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _cell(payload: dict[str, object], zone: str, column: str, rack: str, level: str, depth: str):
    return payload["zones"][zone]["columns"][column]["racks"][rack]["levels"][level]["depths"][
        depth
    ]


def test_standard_locations_are_grouped_by_zone_rack_level_and_depth(
    session: Session,
) -> None:
    _seed_location(
        session, part_key="PART-A", part_name="Part A", location_code="A-A01-011", quantity=2
    )
    _seed_location(
        session, part_key="PART-B", part_name="Part B", location_code="A-A01-012", quantity=3
    )

    payload = build_inventory_location_map(session=session)

    depth_1 = _cell(payload, "A", "A", "1", "1", "1")
    depth_2 = _cell(payload, "A", "A", "1", "1", "2")
    assert depth_1["location_code"] == "A-A01-011"
    assert depth_1["total_quantity"] == 2
    assert depth_1["materials"] == [{"part_key": "PART-A", "part_name": "Part A", "quantity": 2}]
    assert depth_2["location_code"] == "A-A01-012"
    assert depth_2["total_quantity"] == 3
    assert payload["summary"]["standard_location_count"] == 2


def test_same_location_merges_material_rows_and_quantities(session: Session) -> None:
    _seed_location(
        session, part_key="PART-A", part_name="Part A", location_code="A-A01-011", quantity=2
    )
    _seed_location(
        session, part_key="PART-B", part_name="Part B", location_code="A-A01-011", quantity=3
    )
    _seed_location(
        session, part_key="PART-A", part_name="Part A", location_code="A-A01-011", quantity=4
    )

    payload = build_inventory_location_map(session=session)

    cell = _cell(payload, "A", "A", "1", "1", "1")
    assert cell["total_quantity"] == 9
    assert cell["material_count"] == 2
    assert cell["materials"] == [
        {"part_key": "PART-A", "part_name": "Part A", "quantity": 6},
        {"part_key": "PART-B", "part_name": "Part B", "quantity": 3},
    ]
    assert payload["summary"]["standard_location_count"] == 1


def test_non_standard_locations_are_grouped_into_buckets(session: Session) -> None:
    _seed_location(
        session, part_key="TMP", location_code="TMP-01", quantity=1, location_kind="temporary"
    )
    _seed_location(session, part_key="UP", location_code="楼上围栏处", quantity=2)
    _seed_location(session, part_key="RAW", location_code="随便写的位置", quantity=3)

    payload = build_inventory_location_map(session=session)

    assert payload["buckets"]["temporary"][0]["location_code"] == "TMP-01"
    assert payload["buckets"]["upstairs"][0]["location_code"] == "楼上围栏处"
    assert payload["buckets"]["unresolved"][0]["location_code"] == "随便写的位置"
    assert payload["summary"]["temporary_location_count"] == 1
    assert payload["summary"]["upstairs_location_count"] == 1
    assert payload["summary"]["unresolved_location_count"] == 1


def test_mixed_material_warning_and_rack_warning(session: Session) -> None:
    for index in range(5):
        _seed_location(
            session,
            part_key=f"PART-{index}",
            location_code="A-A01-011",
            quantity=1,
        )
    for index in range(5, 10):
        _seed_location(
            session,
            part_key=f"PART-{index}",
            location_code="A-A01-012",
            quantity=1,
        )

    payload = build_inventory_location_map(session=session)

    rack = payload["zones"]["A"]["columns"]["A"]["racks"]["1"]
    assert _cell(payload, "A", "A", "1", "1", "1")["mixed_material_warning"] is True
    assert _cell(payload, "A", "A", "1", "1", "2")["mixed_material_warning"] is True
    assert rack["rack_warning"] is True
    assert "建议整理到 B区或待整理区" in rack["rack_warning_message"]
    assert payload["summary"]["mixed_location_count"] == 2


def test_permanent_zero_stock_cell_marks_restock_required(session: Session) -> None:
    _seed_location(session, part_key="EMPTY", location_code="B-C02-032", quantity=0)

    payload = build_inventory_location_map(session=session)

    cell = _cell(payload, "B", "C", "2", "3", "2")
    assert cell["restock_required"] is True
    assert cell["total_quantity"] == 0
    assert payload["summary"]["restock_required_count"] == 1
