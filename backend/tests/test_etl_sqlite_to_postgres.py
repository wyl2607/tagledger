from pathlib import Path

from scripts.etl_sqlite_to_postgres import (
    _is_postgres_url,
    _normalize_factory_id,
    _normalize_postgres_url,
    _post_commit_counts,
    _reset_postgres_sequence,
)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params or {}))
        if "pg_get_serial_sequence" in sql:
            return FakeResult("records_id_seq")
        return FakeResult(None)


def test_normalize_postgres_url_uses_psycopg_driver() -> None:
    assert (
        _normalize_postgres_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert (
        _normalize_postgres_url("postgres://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert _is_postgres_url("postgresql://user:pass@host:5432/db") is True
    assert _is_postgres_url("postgres://user:pass@host:5432/db") is True
    assert _is_postgres_url(f"sqlite:///{Path('/tmp/test.db')}") is False


def test_normalize_factory_id_backfills_blank_values() -> None:
    assert _normalize_factory_id({"factory_id": None}, "factory_b")["factory_id"] == "factory_b"
    assert _normalize_factory_id({"factory_id": "  "}, "factory_c")["factory_id"] == "factory_c"
    assert (
        _normalize_factory_id({"factory_id": "factory_a"}, "factory_b")["factory_id"] == "factory_a"
    )
    assert _normalize_factory_id({"id": 1}, "factory_b") == {"id": 1}


def test_reset_postgres_sequence_sets_id_sequence_after_copy() -> None:
    connection = FakeConnection()

    assert _reset_postgres_sequence(connection, "records") is True

    assert len(connection.calls) == 2
    lookup_sql, lookup_params = connection.calls[0]
    reset_sql, reset_params = connection.calls[1]
    assert "pg_get_serial_sequence" in lookup_sql
    assert lookup_params == {"table_name": "records", "column_name": "id"}
    assert "setval" in reset_sql
    assert "MAX(id)" in reset_sql
    assert reset_params == {"sequence_name": "records_id_seq"}


def test_post_commit_counts_reads_with_fresh_connection() -> None:
    class FakeTable:
        pass

    class FakeMetadata:
        tables = {
            table_name: FakeTable()
            for table_name in (
                "records",
                "outbound_scans",
                "outbound_progress_snapshots",
                "inventory_locations",
                "inventory_movements",
                "users",
                "user_sessions",
                "audit_logs",
                "security_secrets",
            )
        }

    class FreshConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FreshEngine:
        def __init__(self):
            self.connect_calls = 0

        def connect(self):
            self.connect_calls += 1
            return FreshConnection()

    engine = FreshEngine()

    import scripts.etl_sqlite_to_postgres as etl

    original_row_count = etl._row_count
    try:
        etl._row_count = lambda _connection, _table: 7
        counts = _post_commit_counts(engine, FakeMetadata())
    finally:
        etl._row_count = original_row_count

    assert engine.connect_calls == 1
    assert counts["records"] == 7
    assert counts["security_secrets"] == 7
