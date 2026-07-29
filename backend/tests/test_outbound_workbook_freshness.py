from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.app.services.outbound_reconciliation.excel_loader import assert_file_not_stale


def test_assert_file_not_stale_passes_for_fresh_file(tmp_path: Path) -> None:
    path = tmp_path / "outbound.xlsx"
    path.write_bytes(b"x")
    assert_file_not_stale(path, max_age_days=3, label="outbound workbook")


def test_assert_file_not_stale_fails_for_old_file(tmp_path: Path) -> None:
    path = tmp_path / "outbound.xlsx"
    path.write_bytes(b"x")
    old = time.time() - 10 * 86400
    # touch mtime into the past
    import os

    os.utime(path, (old, old))
    with pytest.raises(RuntimeError, match="stale"):
        assert_file_not_stale(path, max_age_days=3, label="outbound workbook")


def test_assert_file_not_stale_disabled_when_max_age_zero(tmp_path: Path) -> None:
    path = tmp_path / "outbound.xlsx"
    path.write_bytes(b"x")
    import os

    old = time.time() - 100 * 86400
    os.utime(path, (old, old))
    assert_file_not_stale(path, max_age_days=0, label="outbound workbook")
