from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from local_image_search.db import Database
from local_image_search.vector import VectorError, upload_to_crop_vector


def create_app(db_path: str | Path = "./data/index.sqlite") -> FastAPI:
    db_path = Path(db_path)
    app = FastAPI(title="Local Image Search API", version="0.1.0")
    web_root = resources.files("local_image_search").joinpath("web")
    static_root = web_root.joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")

    def open_db() -> Database:
        return Database(db_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return web_root.joinpath("index.html").read_text(encoding="utf-8")

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

    @app.post("/api/search")
    async def search(
        file: UploadFile = File(...),
        x: float = Form(...),
        y: float = Form(...),
        width: float = Form(...),
        height: float = Form(...),
        limit: int = Form(50),
    ) -> dict[str, object]:
        if width <= 0 or height <= 0:
            raise HTTPException(status_code=400, detail="Crop width and height must be positive")
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 500")

        content = await file.read()
        try:
            query_vector = upload_to_crop_vector(content, x=x, y=y, width=width, height=height)
        except VectorError as exc:
            raise HTTPException(status_code=400, detail=f"Could not read query image: {exc}") from exc

        with open_db() as database:
            groups = database.grouped_search_by_vector(query_vector, limit=limit)

        return {
            "model": "rgb-tile-16-v1",
            "groups": groups,
            "limit": limit,
        }

    return app


app = create_app()
