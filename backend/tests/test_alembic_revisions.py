from __future__ import annotations

from pathlib import Path


def test_alembic_revision_ids_fit_postgres_version_column() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    for migration_path in versions_dir.glob("*.py"):
        namespace: dict[str, object] = {}
        exec(migration_path.read_text(encoding="utf-8"), namespace)
        revision = namespace.get("revision")
        if isinstance(revision, str):
            assert len(revision) <= 32, f"{migration_path.name} revision id is too long"
