from pathlib import Path

from PIL import Image

from backend.app.ocr.preprocessor import preprocess_image


def test_preprocess_creates_output_file(tmp_path: Path) -> None:
    img = Image.new("RGB", (100, 100), color="red")
    input_path = tmp_path / "test.png"
    img.save(input_path)

    result = preprocess_image(input_path)

    assert isinstance(result, Path)
    assert result.exists()


def test_preprocess_output_is_grayscale(tmp_path: Path) -> None:
    img = Image.new("RGB", (100, 100), color="blue")
    input_path = tmp_path / "test.png"
    img.save(input_path)

    result = preprocess_image(input_path)

    processed = Image.open(result)
    assert processed.mode == "L"


def test_preprocess_output_name_suffix(tmp_path: Path) -> None:
    img = Image.new("RGB", (100, 100), color="green")
    input_path = tmp_path / "my-image.png"
    img.save(input_path)

    result = preprocess_image(input_path)

    assert result.name == "my-image.preprocessed.png"


def test_preprocess_handles_upgraded_image(tmp_path: Path) -> None:
    img = Image.new("RGB", (3000, 200), color="yellow")
    input_path = tmp_path / "big.png"
    img.save(input_path)

    result = preprocess_image(input_path)

    processed = Image.open(result)
    assert processed.mode == "L"
    assert processed.size[0] >= 2000


def test_preprocess_bad_file_returns_original(tmp_path: Path) -> None:
    not_an_image = tmp_path / "bad.png"
    not_an_image.write_text("not an image")

    result = preprocess_image(not_an_image)

    assert result == not_an_image
