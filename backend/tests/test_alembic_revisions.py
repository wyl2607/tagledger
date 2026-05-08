from __future__ import annotations

from pathlib import Path
from typing import Any


def test_alembic_revision_ids_fit_postgres_version_column() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    for migration_path in versions_dir.glob("*.py"):
        namespace: dict[str, object] = {}
        exec(migration_path.read_text(encoding="utf-8"), namespace)
        revision = namespace.get("revision")
        if isinstance(revision, str):
            assert len(revision) <= 32, f"{migration_path.name} revision id is too long"


def test_alembic_down_revisions_point_to_existing_revision_ids() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    revisions: dict[str, str] = {}
    down_revisions: dict[str, object] = {}
    for migration_path in versions_dir.glob("*.py"):
        namespace: dict[str, Any] = {}
        exec(migration_path.read_text(encoding="utf-8"), namespace)
        revision = namespace.get("revision")
        if isinstance(revision, str):
            revisions[revision] = migration_path.name
            down_revisions[revision] = namespace.get("down_revision")

    missing: dict[str, list[str]] = {}
    for revision, down_revision in down_revisions.items():
        if down_revision is None:
            continue
        parents = [down_revision] if isinstance(down_revision, str) else list(down_revision)
        missing_parents = [parent for parent in parents if parent not in revisions]
        if missing_parents:
            missing[revision] = missing_parents

    assert missing == {}
