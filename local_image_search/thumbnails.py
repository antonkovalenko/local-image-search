from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


THUMB_SIZE = (320, 320)


class ImageDecodeError(RuntimeError):
    pass


def thumbnail_path(thumbs_dir: Path, sha256: str) -> Path:
    return thumbs_dir / sha256[:2] / f"{sha256}.jpg"


def read_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageDecodeError(str(exc)) from exc


def create_thumbnail(source: Path, destination: Path) -> tuple[int, int]:
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            image.thumbnail(THUMB_SIZE)
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(destination, "JPEG", quality=85, optimize=True)
            return width, height
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageDecodeError(str(exc)) from exc
