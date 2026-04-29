from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from rich.progress import Progress

from local_image_search.db import Database, ImageRecord
from local_image_search.files import iter_image_files
from local_image_search.thumbnails import ImageDecodeError, create_thumbnail, thumbnail_path
from local_image_search.vector import DEFAULT_MODEL_NAME, VectorError, get_model


@dataclass
class IndexSummary:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    errors: int = 0
    missing_marked: int = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_paths(
    roots: list[Path],
    db_path: Path,
    thumbs_dir: Path,
    model_name: str = DEFAULT_MODEL_NAME,
) -> IndexSummary:
    summary = IndexSummary()
    thumbs_dir = thumbs_dir.expanduser().resolve()
    model = get_model(model_name)

    with Database(db_path) as db:
        image_paths = sorted({path for root in roots for path in iter_image_files(root)})
        seen_paths = {str(path) for path in image_paths}

        with Progress() as progress:
            task = progress.add_task("Indexing images", total=len(image_paths))
            for path in image_paths:
                summary.scanned += 1
                try:
                    stat = path.stat()
                    existing = db.get_existing(path)
                    if (
                        existing is not None
                        and existing.size_bytes == stat.st_size
                        and existing.mtime_ns == stat.st_mtime_ns
                    ):
                        image_id = db.get_image_id(path)
                        if image_id is not None and not db.has_vector(image_id, model.name):
                            db.upsert_vector(image_id, model.embed_path(path), model.name)
                            summary.indexed += 1
                            progress.advance(task)
                            continue
                        db.touch_seen(path)
                        summary.skipped += 1
                        progress.advance(task)
                        continue

                    sha256 = sha256_file(path)
                    thumb = thumbnail_path(thumbs_dir, sha256)
                    width, height = create_thumbnail(path, thumb)
                    record = ImageRecord(
                        path=str(path),
                        folder=str(path.parent),
                        filename=path.name,
                        extension=path.suffix.lower().lstrip("."),
                        size_bytes=stat.st_size,
                        mtime_ns=stat.st_mtime_ns,
                        sha256=sha256,
                        width=width,
                        height=height,
                        thumb_path=str(thumb),
                    )
                    image_id = db.upsert_image(record)
                    db.upsert_vector(image_id, model.embed_path(path), model.name)
                    summary.indexed += 1
                except (OSError, ImageDecodeError, VectorError) as exc:
                    try:
                        db.mark_error(path, str(exc))
                    except OSError:
                        pass
                    summary.errors += 1
                finally:
                    progress.advance(task)

        summary.missing_marked = db.mark_missing_outside_seen(seen_paths)
        db.conn.commit()

    return summary
