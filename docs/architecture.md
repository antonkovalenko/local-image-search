# Local Image Search Architecture

## Goal

Build a local-first image archive indexer and search tool that can be cloned onto another desktop machine and run with a short setup process. The first milestone is intentionally small: index files, metadata, and thumbnails reliably before adding vector embeddings or a web UI.

## Milestone 1: File And Thumbnail Indexer

M1 provides a command-line tool that can:

- Recursively scan one or more image folders.
- Store image metadata in SQLite.
- Generate thumbnails once and reuse them.
- Skip unchanged files on repeated runs.
- Mark missing files when they disappear from disk.
- Print useful stats.
- Verify that indexed files and thumbnails still exist.

This milestone proves the project works against a real archive and can be deployed by `git clone` plus a few shell commands.

## Runtime Shape

The first version is a single local Python application:

- CLI: `local-image-search`
- Metadata database: SQLite
- Thumbnails: filesystem directory
- Image decoding: Pillow
- Progress output: Rich

No web server, auth, background workers, vector database, or ClickHouse are needed for M1.

## Project Layout

```text
local-image-search/
  docs/
    requirements.md
    architecture.md
    deploy.md
  local_image_search/
    __init__.py
    cli.py
    db.py
    files.py
    indexer.py
    thumbnails.py
  tests/
  data/
    .gitkeep
  pyproject.toml
  requirements.txt
```

## CLI Contract

```bash
local-image-search index /path/to/photos --db ./data/index.sqlite --thumbs ./data/thumbs
local-image-search stats --db ./data/index.sqlite
local-image-search verify --db ./data/index.sqlite
```

`index` is incremental. It uses path, file size, and modification time to skip unchanged files. It computes a content hash only when a file is new or changed.

## SQLite Schema

The M1 database stores only durable metadata:

```sql
images(
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
  indexed_at text not null,
  last_seen_at text not null
)
```

`status` is `active`, `missing`, or `error`.

## Future Milestones

M2 should add embeddings after M1 works on real folders:

- Full-image embeddings with OpenCLIP or SigLIP.
- Face detection and face embeddings for person search.
- Vector index via `sqlite-vec`, `hnswlib`, `FAISS`, or LanceDB.

ClickHouse should be considered later only if the archive is very large or SQL-heavy metadata analysis becomes important.
