from backend.app.services.normalize import normalize_label_value


def test_normalize_none_returns_none() -> None:
    assert normalize_label_value(None) is None


def test_normalize_empty_string_returns_none() -> None:
    assert normalize_label_value("") is None


def test_normalize_whitespace_only_returns_none() -> None:
    assert normalize_label_value("   ") is None
    assert normalize_label_value("\t\n ") is None


def test_normalize_strips_and_uppercases() -> None:
    assert normalize_label_value(" hello ") == "HELLO"


def test_normalize_preserves_inner_whitespace() -> None:
    assert normalize_label_value("  hello  world  ") == "HELLO  WORLD"
