from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class VectorIndex:
    model: str
    matrix: np.ndarray
    items: list[dict[str, Any]]

    def search(self, query_vector: np.ndarray, limit: int = 50) -> list[dict[str, Any]]:
        if self.matrix.size == 0:
            return []

        query = np.asarray(query_vector, dtype=np.float32)
        scores = np.clip(self.matrix @ query, -1.0, 1.0)
        limit = min(limit, scores.shape[0])
        if limit <= 0:
            return []

        candidate_indexes = np.argpartition(scores, -limit)[-limit:]
        ordered_indexes = candidate_indexes[np.argsort(scores[candidate_indexes])[::-1]]
        results = []
        for index in ordered_indexes:
            item = dict(self.items[int(index)])
            item["score"] = float(scores[int(index)])
            results.append(item)
        return results

    def grouped_search(self, query_vector: np.ndarray, limit: int = 50, per_folder: int = 12) -> list[dict[str, Any]]:
        matches = self.search(query_vector, limit=limit)
        folders: dict[str, dict[str, Any]] = {}
        for match in matches:
            folder = match["folder"]
            group = folders.setdefault(
                folder,
                {
                    "folder": folder,
                    "score": match["score"],
                    "representative": match,
                    "images": [],
                },
            )
            group["score"] = max(group["score"], match["score"])
            if len(group["images"]) < per_folder:
                group["images"].append(match)

        return sorted(folders.values(), key=lambda item: item["score"], reverse=True)


def build_vector_index(model: str, rows: list[dict[str, Any]]) -> VectorIndex:
    if not rows:
        return VectorIndex(model=model, matrix=np.empty((0, 0), dtype=np.float32), items=[])

    matrix = np.vstack([row.pop("_vector") for row in rows]).astype(np.float32, copy=False)
    return VectorIndex(model=model, matrix=matrix, items=rows)
