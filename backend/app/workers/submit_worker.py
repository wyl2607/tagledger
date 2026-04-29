import atexit
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlmodel import Session, select

from backend.app.config import get_settings
from backend.app.database import engine
from backend.app.models import Record, RecordStatus, utc_now
from backend.app.saas.client import (
    PlaywrightNotInstalledError,
    SaaSClient,
    SaaSSubmissionError,
)

logger = logging.getLogger(__name__)

BACKOFF_SECONDS = (5, 30, 120)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="submit-worker")


def _shutdown_executor() -> None:
    _executor.shutdown(wait=False)


atexit.register(_shutdown_executor)


def enqueue_submission(record_id: int) -> None:
    try:
        _executor.submit(run, record_id)
    except RuntimeError:
        logger.warning(
            "submit worker pool is shut down; record %s will be retried on restart", record_id
        )


def enqueue_pending_confirmed() -> int:
    with Session(engine) as session:
        records = session.exec(select(Record).where(Record.status == RecordStatus.confirmed)).all()
        for record in records:
            if record.id is not None:
                enqueue_submission(record.id)
        return len(records)


def run(record_id: int) -> None:
    settings = get_settings()
    with Session(engine) as session:
        record = session.get(Record, record_id)
        if record is None or record.status != RecordStatus.confirmed:
            return

    retries = max(settings.submission_retries, 1)
    while True:
        with Session(engine) as session:
            record = session.get(Record, record_id)
            if record is None or record.status != RecordStatus.confirmed:
                return
            attempt_index = record.submission_attempts

        if attempt_index > 0:
            time.sleep(BACKOFF_SECONDS[min(attempt_index - 1, len(BACKOFF_SECONDS) - 1)])

        should_retry = _attempt_submission(record_id, settings)
        if not should_retry:
            return

        with Session(engine) as session:
            record = session.get(Record, record_id)
            if (
                record is None
                or record.status != RecordStatus.confirmed
                or record.submission_attempts >= retries
            ):
                return


def _attempt_submission(record_id: int, settings) -> bool:
    with Session(engine) as session:
        record = session.get(Record, record_id)
        if record is None or record.status != RecordStatus.confirmed:
            return False
        image_path = Path(record.image_path)
        if not image_path.is_absolute():
            image_path = settings.upload_path.parent.parent / record.image_path
        try:
            client = SaaSClient(settings=settings, dry_run=settings.dry_run)
            result = client.submit_record(record, image_path)
        except PlaywrightNotInstalledError as exc:
            record.last_error = str(exc)
            record.updated_at = utc_now()
            session.add(record)
            session.commit()
            _write_playwright_log(
                settings,
                f"SaaS dry-run skipped for record {record_id}: {exc}",
            )
            return False
        except Exception as exc:
            if settings.dry_run and _is_missing_playwright_browser(exc):
                record.last_error = str(exc)
                record.updated_at = utc_now()
                session.add(record)
                session.commit()
                _write_playwright_log(
                    settings,
                    f"SaaS dry-run skipped for record {record_id}: {exc}",
                )
                return False
            screenshot = (
                exc.screenshot_path
                if isinstance(exc, SaaSSubmissionError)
                else _capture_error_screenshot(settings, record)
            )
            record.submission_attempts += 1
            record.last_error = str(exc)
            record.error_screenshot = screenshot
            if record.submission_attempts >= max(settings.submission_retries, 1):
                record.status = RecordStatus.submission_failed
            record.updated_at = utc_now()
            session.add(record)
            session.commit()
            _write_playwright_log(settings, f"SaaS submission failed for record {record_id}: {exc}")
            logger.exception("SaaS submission failed for record %s", record_id)
            return record.status == RecordStatus.confirmed

        record.error_screenshot = result.screenshot_path
        record.last_error = (
            "dry-run complete; real SaaS submit was not clicked" if result.dry_run else None
        )
        if result.dry_run:
            record.updated_at = utc_now()
        else:
            record.status = RecordStatus.submitted
            record.submitted_at = utc_now()
            record.updated_at = record.submitted_at
        session.add(record)
        session.commit()
        _write_playwright_log(
            settings,
            f"SaaS submission {'dry-run' if result.dry_run else 'submitted'} for record {record_id}",
        )
        return False


def _capture_error_screenshot(settings, record: Record) -> str | None:
    # submit_record normally returns the most useful screenshot path. This fallback preserves
    # a trace even for failures before Playwright opens a page or before dry-run capture.
    try:
        ts = utc_now().strftime("%Y%m%dT%H%M%SZ")
        path = settings.screenshot_path / f"error_{record.id}_{ts}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "No browser screenshot was available; see logs/playwright.log and last_error.\n",
            encoding="utf-8",
        )
        return str(path)
    except Exception:
        return None


def _is_missing_playwright_browser(exc: Exception) -> bool:
    message = str(exc)
    return "Executable doesn't exist" in message and "playwright install" in message


def _write_playwright_log(settings, message: str) -> None:
    try:
        settings.playwright_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = utc_now().isoformat()
        with settings.playwright_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except Exception:
        logger.debug("Could not write Playwright log", exc_info=True)
