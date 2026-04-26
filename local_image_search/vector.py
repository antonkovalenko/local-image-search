from __future__ import annotations

import json
import math
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


VECTOR_MODEL = "rgb-tile-16-v1"
VECTOR_SIZE = (16, 16)


class VectorError(RuntimeError):
    pass


def image_to_vector(image: Image.Image) -> list[float]:
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB").resize(VECTOR_SIZE)
    values: list[float] = []
    for red, green, blue in image.getdata():
        values.extend((red / 255.0, green / 255.0, blue / 255.0))
    return normalize(values)


def path_to_vector(path: Path) -> list[float]:
    try:
        with Image.open(path) as image:
            return image_to_vector(image)
    except (OSError, UnidentifiedImageError) as exc:
        raise VectorError(str(exc)) from exc


def upload_to_crop_vector(content: bytes, x: float, y: float, width: float, height: float) -> list[float]:
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)
            image_width, image_height = image.size
            left = clamp(round(x), 0, image_width - 1)
            top = clamp(round(y), 0, image_height - 1)
            right = clamp(round(x + width), left + 1, image_width)
            bottom = clamp(round(y + height), top + 1, image_height)
            return image_to_vector(image.crop((left, top, right, bottom)))
    except (OSError, UnidentifiedImageError) as exc:
        raise VectorError(str(exc)) from exc


def normalize(values: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in values))
    if length == 0:
        return values
    return [value / length for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def encode_vector(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def decode_vector(raw: str) -> list[float]:
    return [float(value) for value in json.loads(raw)]


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
