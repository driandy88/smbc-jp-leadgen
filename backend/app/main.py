"""Hexline API + the built frontend, served from one container."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routers import auth, billing, reviews, scout, versions, websearch
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().execution_mode == "thread":
        from app.services import webagent
        from app.services.collector import recover_interrupted

        recover_interrupted()
        webagent.recover_interrupted()
    yield


app = FastAPI(title="Hexline", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)
for r in (auth.router, scout.router, versions.router, websearch.router, reviews.router, billing.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/public/outline")
def login_outline():
    """Osaka City wards for the sign-in screen map (public boundary data, no auth)."""
    from app.services import regions

    return regions.area_geojson([a["code"] for a in regions.city_areas("osaka-shi", 7)])


dist = Path(get_settings().frontend_dist)
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "design").exists():
        app.mount("/design", StaticFiles(directory=dist / "design", html=True), name="design")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = dist / path
        return FileResponse(f if path and f.is_file() else dist / "index.html")
