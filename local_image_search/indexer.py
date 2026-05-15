from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from rich.progress import Progress

from local_image_search.db import Database, ImageRecord
from local_image_search.files import iter_image_files
from local_image_search.thumbnails import ImageDecodeError, create_thumbnail, thumbnail_path
from local_image_search.vector import DEFAULT_MODEL_NAME, VectorError, get_model


LOGGER_NAME = "local_image_search.indexer"


@dataclass
class IndexSummary:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    errors: int = 0
    missing_marked: int = 0
    log_path: str | None = None


def configure_file_logger(log_path: Path) -> logging.Logger:
    log_path = log_path.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    return logger


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
    log_path: Path | None = None,
) -> IndexSummary:
    summary = IndexSummary()
    thumbs_dir = thumbs_dir.expanduser().resolve()
    logger = configure_file_logger(log_path) if log_path is not None else logging.getLogger(LOGGER_NAME)
    if log_path is not None:
        summary.log_path = str(log_path.expanduser().resolve())

    logger.info(
        "index_start roots=%s db=%s thumbs=%s model=%s",
        [str(root) for root in roots],
        db_path,
        thumbs_dir,
        model_name,
    )

    try:
        model = get_model(model_name)

        with Database(db_path) as db:
            image_paths = sorted({path for root in roots for path in iter_image_files(root)})
            seen_paths = {str(path) for path in image_paths}
            logger.info("scan_complete image_count=%s", len(image_paths))

            with Progress() as progress:
                task = progress.add_task("Indexing images", total=len(image_paths))
                for path in image_paths:
                    summary.scanned += 1
                    logger.info("image_start path=%s", path)
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
                                logger.info("image_vector_indexed path=%s image_id=%s model=%s", path, image_id, model.name)
                                progress.advance(task)
                                continue
                            db.touch_seen(path)
                            summary.skipped += 1
                            logger.info("image_skipped path=%s reason=unchanged model=%s", path, model.name)
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
                        logger.info(
                            "image_indexed path=%s image_id=%s model=%s width=%s height=%s bytes=%s thumb=%s",
                            path,
                            image_id,
                            model.name,
                            width,
                            height,
                            stat.st_size,
                            thumb,
                        )
                    except (OSError, ImageDecodeError, VectorError) as exc:
                        try:
                            db.mark_error(path, str(exc))
                        except OSError:
                            logger.exception("image_mark_error_failed path=%s", path)
                        summary.errors += 1
                        logger.exception("image_error path=%s error=%s", path, exc)
                    finally:
                        progress.advance(task)

            summary.missing_marked = db.mark_missing_outside_seen(seen_paths)
            db.conn.commit()
    except Exception:
        logger.exception("index_crashed")
        raise
    finally:
        logger.info(
            "index_finish scanned=%s indexed=%s skipped=%s errors=%s missing_marked=%s",
            summary.scanned,
            summary.indexed,
            summary.skipped,
            summary.errors,
            summary.missing_marked,
        )

    return summary
