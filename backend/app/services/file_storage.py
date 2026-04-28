from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.app.config import get_settings


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_upload_filename(filename: str | None) -> str:
    if not filename:
        raise ValueError("upload filename is required")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ValueError(f"unsupported image extension: {suffix or '<none>'}; allowed: {allowed}")
    return suffix


def save_upload(file: UploadFile) -> Path:
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    suffix = validate_upload_filename(file.filename)
    target = settings.upload_path / f"{uuid4().hex}{suffix}"
    with target.open("wb") as handle:
        while chunk := file.file.read(1024 * 1024):
            handle.write(chunk)
    return target
