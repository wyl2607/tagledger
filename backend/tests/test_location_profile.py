from backend.app.services.location_profile import (
    location_profile_payload,
    normalize_location_text,
    parse_location_code,
)


def test_normalize_location_text_uppercases_and_compacts_standard_code() -> None:
    assert normalize_location_text(" a-a01-011 ") == "A-A01-011"


def test_parse_standard_location_a_zone_nearest_depth() -> None:
    profile = parse_location_code("A-A01-011")

    assert profile["raw_location_code"] == "A-A01-011"
    assert profile["normalized_location_code"] == "A-A01-011"
    assert profile["parse_status"] == "standard"
    assert profile["zone"] == "A"
    assert profile["aisle_or_column"] == "A"
    assert profile["rack_index"] == 1
    assert profile["level"] == 1
    assert profile["depth"] == 1
    assert profile["centerline_rank"] == 1
    assert profile["sort_key"] == ["standard", "A", "A", 1, 1, 1]
    assert profile["display_label"] == "A区 A列 1号架 1层 近位1"


def test_parse_standard_location_a_zone_level_two_far_depth() -> None:
    profile = parse_location_code("A-A01-023")

    assert profile["parse_status"] == "standard"
    assert profile["zone"] == "A"
    assert profile["aisle_or_column"] == "A"
    assert profile["rack_index"] == 1
    assert profile["level"] == 2
    assert profile["depth"] == 3
    assert profile["centerline_rank"] == 3


def test_parse_standard_location_b_zone_column_c() -> None:
    profile = parse_location_code("B-C02-032")

    assert profile["parse_status"] == "standard"
    assert profile["zone"] == "B"
    assert profile["aisle_or_column"] == "C"
    assert profile["rack_index"] == 2
    assert profile["level"] == 3
    assert profile["depth"] == 2
    assert profile["centerline_rank"] == 2


def test_parse_upstairs_location_by_keyword() -> None:
    profile = parse_location_code("楼上围栏处")

    assert profile["raw_location_code"] == "楼上围栏处"
    assert profile["parse_status"] == "upstairs"
    assert profile["zone"] == "upstairs"
    assert profile["display_label"] == "楼上区域（待精确整理）"


def test_parse_temporary_location_by_keyword_or_tmp_code() -> None:
    tmp_profile = parse_location_code("TMP-01")
    chinese_profile = parse_location_code("临时库位")

    assert tmp_profile["parse_status"] == "temporary"
    assert tmp_profile["zone"] == "temporary"
    assert chinese_profile["parse_status"] == "temporary"
    assert chinese_profile["zone"] == "temporary"


def test_parse_unresolved_location_preserves_raw_code() -> None:
    profile = parse_location_code("随便写的位置")

    assert profile["raw_location_code"] == "随便写的位置"
    assert profile["normalized_location_code"] == "随便写的位置"
    assert profile["parse_status"] == "unresolved"
    assert profile["zone"] == "unresolved"
    assert profile["display_label"] == "待整理库位：随便写的位置"


def test_location_profile_payload_uses_location_kind_for_temporary() -> None:
    profile = location_profile_payload("QA-IN-01", location_kind="temporary")

    assert profile["raw_location_code"] == "QA-IN-01"
    assert profile["parse_status"] == "temporary"
    assert profile["zone"] == "temporary"
