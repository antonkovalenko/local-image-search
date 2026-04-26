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

Check it:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/stats
curl http://127.0.0.1:8000/api/folders
```

## Notes

- The `data/` directory is for local runtime output and should not be committed.
- Re-running `index` skips unchanged files.
- Deleted files are marked as `missing` instead of being removed from the database.
