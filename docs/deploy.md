# Setup And Deploy

These steps install and run Local Image Search from a fresh clone on Linux or macOS.

## Fresh Setup

```bash
git clone https://github.com/antonkovalenko/local-image-search
cd local-image-search
python3 -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

This installs the base app with the lightweight built-in model:

```text
rgb-tile-16-v1
```

## Optional OpenCLIP Setup

Install this only if you want better visual search quality:

```bash
source .venv/bin/activate
pip install -r requirements-openclip.txt
pip install -e . --no-build-isolation
```

This enables:

```text
openclip-vit-b-32
```

The first OpenCLIP indexing run downloads model weights from Hugging Face and caches them locally.

## Index Photos

Fast baseline model:

```bash
local-image-search index /path/to/photos \
  --db ./data/index.sqlite \
  --thumbs ./data/thumbs \
  --model rgb-tile-16-v1 \
  --log ./data/index.log
```

Better OpenCLIP model:

```bash
local-image-search index /path/to/photos \
  --db ./data/index.sqlite \
  --thumbs ./data/thumbs \
  --model openclip-vit-b-32 \
  --log ./data/openclip-index.log
```

You can keep vectors for both models in the same SQLite database.

## Check The Index

```bash
local-image-search stats --db ./data/index.sqlite --model rgb-tile-16-v1
local-image-search stats --db ./data/index.sqlite --model openclip-vit-b-32
local-image-search verify --db ./data/index.sqlite
```

`stats` reports the active image count, folder count, and vector count for the selected model.

## Run The App

```bash
local-image-search serve --db ./data/index.sqlite --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

The browser search panel has a model selector. Choose a model that has already been indexed.

## API Checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/models
curl 'http://127.0.0.1:8000/api/stats?model=openclip-vit-b-32'
curl http://127.0.0.1:8000/api/folders
```

If you indexed while the server was already running, reload the in-memory NumPy vector index:

```bash
curl -X POST 'http://127.0.0.1:8000/api/reload-index?model=openclip-vit-b-32'
```

Or restart the server.

## Upgrade Existing Clone

```bash
cd local-image-search
git pull
source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

If you use OpenCLIP:

```bash
pip install -r requirements-openclip.txt
pip install -e . --no-build-isolation
```

After upgrading from older versions, re-run indexing. This backfills missing vectors and rewrites old JSON vectors into compact `float32` blobs:

```bash
local-image-search index /path/to/photos \
  --db ./data/index.sqlite \
  --thumbs ./data/thumbs \
  --model rgb-tile-16-v1 \
  --log ./data/index.log
```

For OpenCLIP:

```bash
local-image-search index /path/to/photos \
  --db ./data/index.sqlite \
  --thumbs ./data/thumbs \
  --model openclip-vit-b-32 \
  --log ./data/openclip-index.log
```

A second indexing run should skip unchanged files.

## Troubleshooting

- If `openclip-vit-b-32` is unavailable, install `requirements-openclip.txt`.
- If OpenCLIP indexing fails on the first run, check network access to Hugging Face for model-weight download.
- Every indexing run writes a log file. Use `--log ./data/openclip-index.log` for long OpenCLIP runs.
- If search results are empty for a model, run `stats --model <model>` and confirm `Vectors` is nonzero.
- If results look stale after reindexing, restart the server or call `/api/reload-index?model=<model>`.
- The `data/` directory is local runtime output and should not be committed.
