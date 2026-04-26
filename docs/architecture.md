# Local Image Search Architecture

## Goal

Build a local-first image archive indexer and search tool that can be cloned onto another desktop machine and run with a short setup process. The first milestones are intentionally small: index files, metadata, and thumbnails reliably, then expose them through a local API and browser UI before adding vector embeddings.

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
- API and web UI: FastAPI

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
    api.py
    cli.py
    db.py
    files.py
    indexer.py
    thumbnails.py
    web/
      index.html
      static/
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
local-image-search serve --db ./data/index.sqlite --host 127.0.0.1 --port 8000
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

M2 adds a small local API over the existing index:

- `GET /health`
- `GET /`
- `GET /api/stats`
- `GET /api/verify`
- `GET /api/folders`
- `GET /api/images`
- `GET /api/images/{image_id}`
- `GET /api/images/{image_id}/thumbnail`

M3 adds a minimal browser UI:

- Open `http://127.0.0.1:8000/`.
- Inspect folders grouped from the index.
- Browse thumbnails for a selected folder.
- Preview image metadata.

M4 adds the first end-to-end crop search:

- Index a small deterministic `rgb-tile-16-v1` vector for each image.
- Upload a query image in the browser.
- Draw a crop rectangle on the query image.
- Search active indexed vectors by cosine similarity.
- Return matches grouped by folder.

This is intentionally a baseline vector model. It proves the product flow without requiring large model downloads.

M5 should replace or supplement the baseline vector with ML embeddings:

- Full-image embeddings with OpenCLIP or SigLIP.
- Face detection and face embeddings for person search.
- Vector index via `sqlite-vec`, `hnswlib`, `FAISS`, or LanceDB.

ClickHouse should be considered later only if the archive is very large or SQL-heavy metadata analysis becomes important.
