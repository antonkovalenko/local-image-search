from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
create table if not exists images (
  id integer primary key,
  path text not null unique,
  folder text not null,
  filename text not null,
  extension text not null,
  size_bytes integer not null,
  mtime_ns integer not null,
  sha256 text not null,
  width integer not null,
  height integer not null,
  thumb_path text not null,
  status text not null,
  error text,
  indexed_at text not null,
  last_seen_at text not null
);

create index if not exists idx_images_folder on images(folder);
create index if not exists idx_images_status on images(status);
create index if not exists idx_images_sha256 on images(sha256);
"""


@dataclass(frozen=True)
class ExistingImage:
    path: str
    size_bytes: int
    mtime_ns: int
    status: str


@dataclass(frozen=True)
class ImageRecord:
    path: str
    folder: str
    filename: str
    extension: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    width: int
    height: int
    thumb_path: str
    status: str = "active"
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("pragma journal_mode = wal")
        self.conn.execute("pragma foreign_keys = on")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get_existing(self, path: Path) -> ExistingImage | None:
        row = self.conn.execute(
            "select path, size_bytes, mtime_ns, status from images where path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return ExistingImage(
            path=row["path"],
            size_bytes=row["size_bytes"],
            mtime_ns=row["mtime_ns"],
            status=row["status"],
        )

    def upsert_image(self, record: ImageRecord) -> None:
        now = utc_now()
        self.conn.execute(
            """
            insert into images (
              path, folder, filename, extension, size_bytes, mtime_ns, sha256,
              width, height, thumb_path, status, error, indexed_at, last_seen_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(path) do update set
              folder = excluded.folder,
              filename = excluded.filename,
              extension = excluded.extension,
              size_bytes = excluded.size_bytes,
              mtime_ns = excluded.mtime_ns,
              sha256 = excluded.sha256,
              width = excluded.width,
              height = excluded.height,
              thumb_path = excluded.thumb_path,
              status = excluded.status,
              error = excluded.error,
              indexed_at = excluded.indexed_at,
              last_seen_at = excluded.last_seen_at
            """,
            (
                record.path,
                record.folder,
                record.filename,
                record.extension,
                record.size_bytes,
                record.mtime_ns,
                record.sha256,
                record.width,
                record.height,
                record.thumb_path,
                record.status,
                record.error,
                now,
                now,
            ),
        )

    def touch_seen(self, path: Path) -> None:
        self.conn.execute(
            "update images set status = 'active', error = null, last_seen_at = ? where path = ?",
            (utc_now(), str(path)),
        )

    def mark_error(self, path: Path, error: str) -> None:
        stat = path.stat()
        now = utc_now()
        self.conn.execute(
            """
            insert into images (
              path, folder, filename, extension, size_bytes, mtime_ns, sha256,
              width, height, thumb_path, status, error, indexed_at, last_seen_at
            )
            values (?, ?, ?, ?, ?, ?, '', 0, 0, '', 'error', ?, ?, ?)
            on conflict(path) do update set
              size_bytes = excluded.size_bytes,
              mtime_ns = excluded.mtime_ns,
              status = 'error',
              error = excluded.error,
              indexed_at = excluded.indexed_at,
              last_seen_at = excluded.last_seen_at
            """,
            (
                str(path),
                str(path.parent),
                path.name,
                path.suffix.lower().lstrip("."),
                stat.st_size,
                stat.st_mtime_ns,
                error[:1000],
                now,
                now,
            ),
        )

    def mark_missing_outside_seen(self, seen_paths: set[str]) -> int:
        active_paths = {
            row["path"]
            for row in self.conn.execute("select path from images where status != 'missing'")
        }
        missing = sorted(active_paths - seen_paths)
        if not missing:
            return 0
        self.conn.executemany(
            "update images set status = 'missing' where path = ?",
            [(path,) for path in missing],
        )
        return len(missing)

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute(
            "select status, count(*) as count from images group by status"
        ).fetchall()
        result = {row["status"]: row["count"] for row in rows}
        result["total"] = sum(result.values())
        result["folders"] = self.conn.execute(
            "select count(distinct folder) from images where status = 'active'"
        ).fetchone()[0]
        return result

    def folders(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            with ranked as (
              select
                id,
                folder,
                path,
                filename,
                width,
                height,
                thumb_path,
                mtime_ns,
                row_number() over (
                  partition by folder
                  order by mtime_ns desc, filename asc
                ) as row_number
              from images
              where status = 'active'
            ),
            counts as (
              select folder, count(*) as image_count
              from images
              where status = 'active'
              group by folder
            )
            select
              ranked.folder,
              counts.image_count,
              ranked.id as representative_id,
              ranked.path as representative_path,
              ranked.filename as representative_filename,
              ranked.width as representative_width,
              ranked.height as representative_height,
              ranked.thumb_path as representative_thumb_path
            from ranked
            join counts on counts.folder = ranked.folder
            where ranked.row_number = 1
            order by ranked.folder
            limit ? offset ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def images(self, folder: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if folder is None:
            rows = self.conn.execute(
                """
                select id, path, folder, filename, extension, size_bytes, width, height,
                  thumb_path, indexed_at, last_seen_at
                from images
                where status = 'active'
                order by folder, filename
                limit ? offset ?
                """,
                (limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                select id, path, folder, filename, extension, size_bytes, width, height,
                  thumb_path, indexed_at, last_seen_at
                from images
                where status = 'active' and folder = ?
                order by filename
                limit ? offset ?
                """,
                (folder, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def image(self, image_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            select id, path, folder, filename, extension, size_bytes, width, height,
              thumb_path, status, error, indexed_at, last_seen_at
            from images
            where id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def verify(self) -> dict[str, int]:
        rows = self.conn.execute(
            "select path, thumb_path, status from images where status = 'active'"
        ).fetchall()
        missing_files = 0
        missing_thumbnails = 0
        for row in rows:
            if not Path(row["path"]).exists():
                missing_files += 1
            if row["thumb_path"] and not Path(row["thumb_path"]).exists():
                missing_thumbnails += 1
        return {
            "active": len(rows),
            "missing_files": missing_files,
            "missing_thumbnails": missing_thumbnails,
        }
