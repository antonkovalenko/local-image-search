# Deploy

These steps install the local indexer from a fresh clone on a desktop Linux or macOS machine.

## Setup

```bash
git clone <repo-url>
cd local-image-search
python3 -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

## Run

Index a folder:

```bash
local-image-search index /path/to/photos --db ./data/index.sqlite --thumbs ./data/thumbs
```

Choose an embedding model explicitly:

```bash
local-image-search index /path/to/photos --db ./data/index.sqlite --thumbs ./data/thumbs --model rgb-tile-16-v1
```

Show database stats:

```bash
local-image-search stats --db ./data/index.sqlite
```

Verify indexed files and thumbnails:

```bash
local-image-search verify --db ./data/index.sqlite
```

Run the local API:

```bash
local-image-search serve --db ./data/index.sqlite --host 127.0.0.1 --port 8000
```

Open the browser UI:

```text
http://127.0.0.1:8000/
```

Check it:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/stats
curl http://127.0.0.1:8000/api/folders
```

## Upgrade An Existing Clone

Pull the latest code and refresh the virtual environment:

```bash
cd local-image-search
git pull
source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

Re-run indexing after upgrading to the NumPy vector index:

```bash
local-image-search index /path/to/photos --db ./data/index.sqlite --thumbs ./data/thumbs --model rgb-tile-16-v1
```

This rewrites old JSON vectors into compact `float32` blobs. A second run should skip unchanged files:

```bash
local-image-search index /path/to/photos --db ./data/index.sqlite --thumbs ./data/thumbs --model rgb-tile-16-v1
```

Confirm the vector count:

```bash
local-image-search stats --db ./data/index.sqlite --model rgb-tile-16-v1
```

Start the UI:

```bash
local-image-search serve --db ./data/index.sqlite --host 127.0.0.1 --port 8000
```

If the server was already running while you reindexed, either restart it or reload its in-memory vector index:

```bash
curl -X POST http://127.0.0.1:8000/api/reload-index
```

## Notes

- The `data/` directory is for local runtime output and should not be committed.
- Re-running `index` skips unchanged files.
- Re-running `index` also backfills or rewrites visual vectors for older indexes.
- Deleted files are marked as `missing` instead of being removed from the database.
