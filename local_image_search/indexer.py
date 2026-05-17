from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rich.progress import Progress

from local_image_search.db import Database, ImageRecord
from local_image_search.files import iter_image_files
from local_image_search.thumbnails import ImageDecodeError, create_thumbnail, thumbnail_path
from local_image_search.vector import DEFAULT_MODEL_NAME, EmbeddingModel, VectorError, get_model


LOGGER_NAME = "local_image_search.indexer"


@dataclass
class IndexSummary:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    errors: int = 0
    missing_marked: int = 0
    log_path: str | None = None


@dataclass
class VectorJob:
    path: Path
    image_id: int
    kind: str
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    thumb_path: Path | None = None


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


def process_vector_jobs(
    jobs: list[VectorJob],
    db: Database,
    model: EmbeddingModel,
    summary: IndexSummary,
    logger: logging.Logger,
    progress: Progress,
    task: object,
) -> None:
    if not jobs:
        return

    logger.info("vector_batch_start model=%s count=%s", model.name, len(jobs))
    try:
        vectors = model.embed_paths(job.path for job in jobs)
    except VectorError as exc:
        logger.exception("vector_batch_error model=%s count=%s error=%s", model.name, len(jobs), exc)
        process_vector_jobs_one_by_one(jobs, db, model, summary, logger, progress, task)
        jobs.clear()
        return

    for job, vector in zip(jobs, vectors):
        db.upsert_vector(job.image_id, vector, model.name)
        summary.indexed += 1
        log_vector_success(job, model, logger)
        progress.advance(task)

    db.conn.commit()
    logger.info("vector_batch_finish model=%s count=%s", model.name, len(jobs))
    jobs.clear()


def process_vector_jobs_one_by_one(
    jobs: Iterable[VectorJob],
    db: Database,
    model: EmbeddingModel,
    summary: IndexSummary,
    logger: logging.Logger,
    progress: Progress,
    task: object,
) -> None:
    for job in jobs:
        try:
            vector = model.embed_path(job.path)
            db.upsert_vector(job.image_id, vector, model.name)
            summary.indexed += 1
            log_vector_success(job, model, logger)
        except (OSError, VectorError) as exc:
            try:
                db.mark_error(job.path, str(exc))
            except OSError:
                logger.exception("image_mark_error_failed path=%s", job.path)
            summary.errors += 1
            logger.exception("image_error path=%s error=%s", job.path, exc)
        finally:
            progress.advance(task)
    db.conn.commit()


def log_vector_success(job: VectorJob, model: EmbeddingModel, logger: logging.Logger) -> None:
    if job.kind == "vector":
        logger.info("image_vector_indexed path=%s image_id=%s model=%s", job.path, job.image_id, model.name)
    else:
        logger.info(
            "image_indexed path=%s image_id=%s model=%s width=%s height=%s bytes=%s thumb=%s",
            job.path,
            job.image_id,
            model.name,
            job.width,
            job.height,
            job.size_bytes,
            job.thumb_path,
        )


def index_paths(
    roots: list[Path],
    db_path: Path,
    thumbs_dir: Path,
    model_name: str = DEFAULT_MODEL_NAME,
    log_path: Path | None = None,
    batch_size: int = 16,
    device: str = "auto",
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
        if batch_size < 1:
            raise VectorError("Batch size must be at least 1")

        model = get_model(model_name)
        model.configure(device)

        with Database(db_path) as db:
            image_paths = sorted({path for root in roots for path in iter_image_files(root)})
            seen_paths = {str(path) for path in image_paths}
            logger.info("scan_complete image_count=%s", len(image_paths))

            with Progress() as progress:
                task = progress.add_task("Indexing images", total=len(image_paths))
                vector_jobs: list[VectorJob] = []
                for path in image_paths:
                    summary.scanned += 1
                    logger.info("image_start path=%s", path)
                    advanced_current = False
                    queued_current = False
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
                                vector_jobs.append(VectorJob(path=path, image_id=image_id, kind="vector"))
                                queued_current = True
                                logger.info("image_vector_queued path=%s image_id=%s model=%s", path, image_id, model.name)
                                if len(vector_jobs) >= batch_size:
                                    process_vector_jobs(vector_jobs, db, model, summary, logger, progress, task)
                                    advanced_current = True
                                    queued_current = False
                                continue
                            db.touch_seen(path)
                            summary.skipped += 1
                            logger.info("image_skipped path=%s reason=unchanged model=%s", path, model.name)
                            progress.advance(task)
                            advanced_current = True
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
                        vector_jobs.append(
                            VectorJob(
                                path=path,
                                image_id=image_id,
                                kind="image",
                                width=width,
                                height=height,
                                size_bytes=stat.st_size,
                                thumb_path=thumb,
                            )
                        )
                        queued_current = True
                        logger.info("image_queued path=%s image_id=%s model=%s", path, image_id, model.name)
                        if len(vector_jobs) >= batch_size:
                            process_vector_jobs(vector_jobs, db, model, summary, logger, progress, task)
                            advanced_current = True
                            queued_current = False
                    except (OSError, ImageDecodeError, VectorError) as exc:
                        try:
                            db.mark_error(path, str(exc))
                        except OSError:
                            logger.exception("image_mark_error_failed path=%s", path)
                        summary.errors += 1
                        logger.exception("image_error path=%s error=%s", path, exc)
                        if not advanced_current:
                            progress.advance(task)
                            advanced_current = True
                    finally:
                        if not advanced_current and not queued_current:
                            progress.advance(task)

                process_vector_jobs(vector_jobs, db, model, summary, logger, progress, task)
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
