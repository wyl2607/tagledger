from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile

from backend.app import config as config_module
from backend.app.services.file_storage import (
    ALLOWED_IMAGE_EXTENSIONS,
    save_upload,
    validate_upload_filename,
)


def make_upload_file(filename: str, content: bytes = b"fake-image-data") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_save_upload_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.services.file_storage as fs_module

    monkeypatch.setattr(
        fs_module,
        "get_settings",
        lambda: config_module.Settings(
            upload_dir=str(tmp_path),
        ),
    )

    upload = make_upload_file("photo.jpg")

    result = save_upload(upload)

    assert isinstance(result, Path)
    assert result.exists()
    assert result.read_bytes() == b"fake-image-data"


def test_save_upload_rejects_unsupported_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.app.services.file_storage as fs_module

    monkeypatch.setattr(
        fs_module,
        "get_settings",
        lambda: config_module.Settings(
            upload_dir=str(tmp_path),
        ),
    )

    for filename in ["notes.txt", "script.exe", "doc.pdf"]:
        upload = make_upload_file(filename)
        with pytest.raises(ValueError):
            save_upload(upload)


def test_save_upload_accepts_supported_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.app.services.file_storage as fs_module

    monkeypatch.setattr(
        fs_module,
        "get_settings",
        lambda: config_module.Settings(
            upload_dir=str(tmp_path),
        ),
    )

    for filename in ["a.jpg", "b.jpeg", "c.png", "d.webp"]:
        upload = make_upload_file(filename)
        result = save_upload(upload)
        assert result.exists()


def test_validate_upload_filename_allows_all_image_types() -> None:
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        assert validate_upload_filename(f"image{ext}") == ext

    assert validate_upload_filename("UPPERCASE.JPG") == ".jpg"


def test_validate_upload_filename_raises_on_invalid() -> None:
    tests = [
        ("notes.txt", "extension"),
        ("no_ext", "extension"),
        ("", "filename is required"),
        (None, "filename is required"),
    ]

    for filename, keyword in tests:
        with pytest.raises(ValueError, match=keyword):
            validate_upload_filename(filename)
