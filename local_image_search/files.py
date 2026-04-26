from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def iter_image_files(root: Path) -> Iterator[Path]:
    root = root.expanduser().resolve()
    if root.is_file():
        if is_supported_image(root):
            yield root
        return

    for path in root.rglob("*"):
        if is_supported_image(path):
            yield path
