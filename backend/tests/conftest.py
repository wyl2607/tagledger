from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from backend.app.database import get_session
from backend.app.main import app
from backend.app.models import Record, User
from backend.app.ocr.mock_provider import MockOCRProvider
from backend.app.routes.confirm import get_submit_runner
from backend.app.routes.upload import get_ocr_runner
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)
from backend.app.workers import ocr_worker


def set_authenticated_session(
    client: TestClient,
    token: str,
    csrf_token: str = "pytest-csrf-token",
) -> None:
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf_token)
    client.headers.update({CSRF_HEADER: csrf_token})


@pytest.fixture()
def session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
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
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client(session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    from backend.app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "lan_guard_enabled", False)
    monkeypatch.setattr(settings, "pairing_enabled", False)

    def override_get_session() -> Generator[Session, None, None]:
        yield session

    def override_ocr_runner(record_id: int) -> None:
        record = session.get(Record, record_id)
        if record is not None:
            original_get_ocr_provider = ocr_worker.get_ocr_provider
            original_get_barcode_provider = ocr_worker.get_barcode_provider
            ocr_worker.get_ocr_provider = MockOCRProvider
            ocr_worker.get_barcode_provider = lambda: None
            try:
                ocr_worker.process_record_ocr(session, record)
            finally:
                ocr_worker.get_ocr_provider = original_get_ocr_provider
                ocr_worker.get_barcode_provider = original_get_barcode_provider

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_ocr_runner] = lambda: override_ocr_runner
    app.dependency_overrides[get_submit_runner] = lambda: lambda record_id: None
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides = previous_overrides


@pytest.fixture()
def authenticated_client(client: TestClient, session: Session) -> TestClient:
    user = create_user(
        session,
        username="pytest-user",
        display_name="Pytest User",
        password="pytest-user-pass",
        role="manager",
    )
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    set_authenticated_session(client, token)
    return client


@pytest.fixture()
def authenticate_client(client: TestClient, session: Session):
    def login(user: User, csrf_token: str = "pytest-csrf-token") -> str:
        token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
        set_authenticated_session(client, token, csrf_token)
        return token

    return login
