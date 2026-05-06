from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.app.saas.session import SaaSSession


@pytest.fixture
def session(tmp_path: Path) -> SaaSSession:
    return SaaSSession(storage_state_path=tmp_path / "state.json")


def test_session_construct_accepts_path(tmp_path: Path) -> None:
    s = SaaSSession(tmp_path / "state.json")
    assert s.storage_state_path == tmp_path / "state.json"


def test_context_options_when_state_missing(session: SaaSSession) -> None:
    assert session.context_options() == {}


def test_context_options_when_state_exists(session: SaaSSession) -> None:
    session.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    session.storage_state_path.write_text('{"cookies": []}')

    result = session.context_options()
    assert "storage_state" in result
    assert result["storage_state"] == str(session.storage_state_path)


def test_ensure_login_skips_when_state_exists(session: SaaSSession) -> None:
    session.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    session.storage_state_path.write_text('{"cookies": []}')

    context = MagicMock()
    login = MagicMock()

    session.ensure_login(context, login, "https://example.com/login")

    context.new_page.assert_not_called()
    login.assert_not_called()


def test_ensure_login_calls_login_when_state_missing(session: SaaSSession) -> None:
    context = MagicMock()
    login = MagicMock()

    session.ensure_login(context, login, "https://example.com/login")

    context.new_page.assert_called_once()
    login.assert_called_once()


def test_refresh_login_deletes_old_state_and_logs_in(session: SaaSSession) -> None:
    session.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    session.storage_state_path.write_text('{"cookies": []}')

    context = MagicMock()
    login = MagicMock()

    session.refresh_login(context, login, "https://example.com/login")

    context.new_page.assert_called_once()
    login.assert_called_once()
    assert context.storage_state.called
