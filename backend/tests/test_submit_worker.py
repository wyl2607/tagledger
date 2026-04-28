from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from backend.app.config import Settings
from backend.app.models import Category, Record, RecordStatus
from backend.app.saas.client import PlaywrightNotInstalledError
from backend.app.workers import submit_worker


def test_dry_run_skip_when_playwright_missing_keeps_record_confirmed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class MissingPlaywrightClient:
        def __init__(self, settings, dry_run: bool) -> None:
            self.settings = settings
            self.dry_run = dry_run

        def submit_record(self, record: Record, image_path: Path):
            raise PlaywrightNotInstalledError("Playwright browser is not installed")

    settings = Settings(
        screenshot_dir=str(tmp_path / "screenshots"),
        playwright_log=str(tmp_path / "playwright.log"),
        dry_run=True,
    )
    engine = submit_worker.engine
    record_id: int
    unique_vin = f"VIN-WORKER-{uuid4().hex[:8]}"
    with Session(engine) as session:
        record = Record(
            image_path=str(tmp_path / "label.jpg"),
            category=Category.A,
            vin_or_bin=unique_vin,
            status=RecordStatus.confirmed,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        record_id = record.id or 0

    monkeypatch.setattr(submit_worker, "SaaSClient", MissingPlaywrightClient)

    should_retry = submit_worker._attempt_submission(record_id, settings)

    assert should_retry is False
    with Session(engine) as session:
        record = session.get(Record, record_id)
        assert record is not None
        assert record.status == RecordStatus.confirmed
        assert record.submission_attempts == 0
        assert "Playwright browser is not installed" in (record.last_error or "")


def test_dry_run_skip_when_playwright_browser_missing_keeps_record_confirmed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class MissingBrowserClient:
        def __init__(self, settings, dry_run: bool) -> None:
            self.settings = settings
            self.dry_run = dry_run

        def submit_record(self, record: Record, image_path: Path):
            raise RuntimeError(
                "BrowserType.launch: Executable doesn't exist. Run: playwright install"
            )

    settings = Settings(
        screenshot_dir=str(tmp_path / "screenshots"),
        playwright_log=str(tmp_path / "playwright.log"),
        dry_run=True,
    )
    engine = submit_worker.engine
    record_id: int
    vin = f"VIN-BROWSER-{uuid4().hex}"
    with Session(engine) as session:
        record = Record(
            image_path=str(tmp_path / "label.jpg"),
            category=Category.A,
            vin_or_bin=vin,
            status=RecordStatus.confirmed,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        record_id = record.id or 0

    monkeypatch.setattr(submit_worker, "SaaSClient", MissingBrowserClient)

    should_retry = submit_worker._attempt_submission(record_id, settings)

    assert should_retry is False
    with Session(engine) as session:
        record = session.get(Record, record_id)
        assert record is not None
        assert record.status == RecordStatus.confirmed
        assert record.submission_attempts == 0
        assert "Executable doesn't exist" in (record.last_error or "")
