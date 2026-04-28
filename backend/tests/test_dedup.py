from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from backend.app.models import Category, Record, RecordStatus
from backend.app.services.dedup import find_duplicates, serialize_duplicates
from backend.app.services.file_storage import validate_upload_filename


def make_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ux_records_vin_or_bin "
                "ON records(vin_or_bin) "
                "WHERE vin_or_bin IS NOT NULL AND status != 'duplicate'"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ux_records_serial_number "
                "ON records(serial_number) "
                "WHERE serial_number IS NOT NULL AND status != 'duplicate'"
            )
        )
    return Session(engine)


def test_find_duplicates_by_vin_or_serial(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = Record(
        image_path="sample.jpg",
        category=Category.A,
        vin_or_bin="VIN001",
        serial_number="SN001",
        status=RecordStatus.confirmed,
    )
    session.add(record)
    session.commit()

    duplicates = find_duplicates(session, vin_or_bin="vin001", serial_number=None)

    assert len(duplicates) == 1
    assert duplicates[0].vin_or_bin == "VIN001"


def test_find_duplicates_ignores_blank_values(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = Record(
        image_path="sample.jpg",
        category=Category.A,
        vin_or_bin="VIN-BLANK",
        serial_number="SN-BLANK",
    )
    session.add(record)
    session.commit()

    assert find_duplicates(session, vin_or_bin="   ", serial_number="") == []


def test_find_duplicates_excludes_duplicate_status_records(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = Record(
        image_path="sample.jpg",
        category=Category.A,
        vin_or_bin="VIN-DUP",
        serial_number="SN-DUP",
        status=RecordStatus.duplicate,
    )
    session.add(record)
    session.commit()

    assert find_duplicates(session, vin_or_bin="VIN-DUP", serial_number="SN-DUP") == []


def test_find_duplicates_excludes_current_record(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = Record(
        image_path="sample.jpg",
        category=Category.B,
        vin_or_bin="VIN002",
        serial_number="SN002",
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    duplicates = find_duplicates(
        session,
        vin_or_bin="VIN002",
        serial_number="SN002",
        exclude_id=record.id,
    )

    assert duplicates == []


def test_serialize_duplicates_returns_public_shape(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = Record(
        image_path="sample.jpg",
        category=Category.C,
        model="MX",
        vin_or_bin="VIN003",
        serial_number="SN003",
        status=RecordStatus.confirmed,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    payload = serialize_duplicates([record])

    assert payload[0].id == record.id
    assert payload[0].model == "MX"
    assert payload[0].status == RecordStatus.confirmed


def test_validate_upload_filename_allows_images_and_rejects_other_files() -> None:
    assert validate_upload_filename("label.JPG") == ".jpg"
    assert validate_upload_filename("label.webp") == ".webp"

    for filename in ["notes.txt", "label", "", None]:
        try:
            validate_upload_filename(filename)
        except ValueError as exc:
            assert "extension" in str(exc) or "filename is required" in str(exc)
        else:
            raise AssertionError("expected ValueError")
