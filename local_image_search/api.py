from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from local_image_search.db import Database


def create_app(db_path: str | Path = "./data/index.sqlite") -> FastAPI:
    db_path = Path(db_path)
    app = FastAPI(title="Local Image Search API", version="0.1.0")

    def open_db() -> Database:
        return Database(db_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/stats")
    def stats() -> dict[str, int]:
        with open_db() as database:
            return database.stats()

    @app.get("/api/verify")
    def verify() -> dict[str, int]:
        with open_db() as database:
            return database.verify()

    @app.get("/api/folders")
    def folders(
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        with open_db() as database:
            items = database.folders(limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}

    @app.get("/api/images")
    def images(
        folder: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        with open_db() as database:
            items = database.images(folder=folder, limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}

    @app.get("/api/images/{image_id}")
    def image(image_id: int) -> dict[str, object]:
        with open_db() as database:
            item = database.image(image_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Image not found")
        return item

    @app.get("/api/images/{image_id}/thumbnail")
    def thumbnail(image_id: int) -> FileResponse:
        with open_db() as database:
            item = database.image(image_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Image not found")

        thumb_path = Path(str(item["thumb_path"]))
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not found")

        return FileResponse(thumb_path, media_type="image/jpeg")

    return app


app = create_app()
