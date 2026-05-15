from __future__ import annotations

import json
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


DEFAULT_MODEL_NAME = "rgb-tile-16-v1"
OPENCLIP_MODEL_NAME = "openclip-vit-b-32"
VECTOR_SIZE = (16, 16)


class VectorError(RuntimeError):
    pass


class EmbeddingModel(ABC):
    name: str
    dim: int

    @abstractmethod
    def embed_image(self, image: Image.Image) -> np.ndarray:
        raise NotImplementedError

    def embed_path(self, path: Path) -> np.ndarray:
        try:
            with Image.open(path) as image:
                return self.embed_image(image)
        except (OSError, UnidentifiedImageError) as exc:
            raise VectorError(str(exc)) from exc

    def embed_upload_crop(self, content: bytes, x: float, y: float, width: float, height: float) -> np.ndarray:
        try:
            with Image.open(BytesIO(content)) as image:
                image = ImageOps.exif_transpose(image)
                image_width, image_height = image.size
                left = clamp(round(x), 0, image_width - 1)
                top = clamp(round(y), 0, image_height - 1)
                right = clamp(round(x + width), left + 1, image_width)
                bottom = clamp(round(y + height), top + 1, image_height)
                return self.embed_image(image.crop((left, top, right, bottom)))
        except (OSError, UnidentifiedImageError) as exc:
            raise VectorError(str(exc)) from exc


class RgbTileEmbeddingModel(EmbeddingModel):
    name = DEFAULT_MODEL_NAME
    dim = VECTOR_SIZE[0] * VECTOR_SIZE[1] * 3

    def embed_image(self, image: Image.Image) -> np.ndarray:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB").resize(VECTOR_SIZE)
        vector = np.asarray(image, dtype=np.float32).reshape(-1) / 255.0
        return normalize(vector)


class OpenClipVitB32EmbeddingModel(EmbeddingModel):
    name = OPENCLIP_MODEL_NAME
    dim = 512

    def __init__(self) -> None:
        self._loaded = None

    def embed_image(self, image: Image.Image) -> np.ndarray:
        model, preprocess, torch, device = self._load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        tensor = preprocess(image).unsqueeze(0).to(device)
        with torch.no_grad():
            features = model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.squeeze(0).detach().cpu().numpy().astype(np.float32)

    def _load(self):
        if self._loaded is not None:
            return self._loaded

        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise VectorError(
                "OpenCLIP dependencies are not installed. Run: "
                "pip install -r requirements-openclip.txt"
            ) from exc

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        try:
            model, _, preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32",
                pretrained="laion2b_s34b_b79k",
                device=device,
            )
        except Exception as exc:
            raise VectorError(f"Could not load OpenCLIP model weights: {exc}") from exc
        model.eval()
        self._loaded = (model, preprocess, torch, device)
        return self._loaded


MODELS: dict[str, EmbeddingModel] = {
    DEFAULT_MODEL_NAME: RgbTileEmbeddingModel(),
    OPENCLIP_MODEL_NAME: OpenClipVitB32EmbeddingModel(),
}


def get_model(name: str = DEFAULT_MODEL_NAME) -> EmbeddingModel:
    try:
        return MODELS[name]
    except KeyError as exc:
        available = ", ".join(sorted(MODELS))
        raise VectorError(f"Unknown model '{name}'. Available models: {available}") from exc


def available_models() -> list[str]:
    return sorted(MODELS)


def normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    length = np.linalg.norm(vector)
    if length == 0:
        return vector
    return vector / length


def encode_vector(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def decode_vector(raw: Union[bytes, str], dim: int) -> np.ndarray:
    if isinstance(raw, bytes):
        vector = np.frombuffer(raw, dtype=np.float32)
    else:
        # Compatibility path for rows written by the old JSON vector storage.
        vector = np.asarray(json.loads(raw), dtype=np.float32)
    if vector.shape[0] != dim:
        raise VectorError(f"Vector dim mismatch: expected {dim}, got {vector.shape[0]}")
    return vector


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
