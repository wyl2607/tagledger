import logging
from pathlib import Path


def preprocess_image(image_path: Path) -> Path:
    try:
        from PIL import Image, ImageEnhance, ImageOps

        with Image.open(image_path) as img:
            processed = img.convert("L")
            width, height = processed.size
            if width < 2000:
                scale = 2000 / width
                processed = processed.resize(
                    (2000, int(height * scale)),
                    Image.Resampling.LANCZOS,
                )
            processed = ImageEnhance.Contrast(processed).enhance(1.5)
            processed = ImageOps.autocontrast(processed)

            output_path = image_path.with_name(f"{image_path.stem}.preprocessed.png")
            processed.save(output_path)
            return output_path
    except Exception as exc:
        logging.warning("Failed to preprocess OCR image %s: %s", image_path, exc)
        return image_path
