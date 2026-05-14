"""
FastAPI application entry point.

Creates the app, mounts static directories, initializes the database,
and includes all route modules.
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

# Ensure the project root is on sys.path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.database import init_db
from app.routes.videos import router as videos_router
from app.routes.tags import router as tags_router

app = FastAPI(title="Video Bank")

# Mount static directories for uploaded files
uploads_dir = _project_root / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "videos").mkdir(parents=True, exist_ok=True)
(uploads_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Include routers
app.include_router(videos_router)
app.include_router(tags_router)

# Templates for error pages
templates = Jinja2Templates(directory=str(_project_root / "app" / "templates"))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """Return a styled error page for HTTP errors."""
    return templates.TemplateResponse(
        request, "error.html",
        {"status_code": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Override 404 with a custom template."""
    return templates.TemplateResponse(
        request, "error.html",
        {"status_code": 404, "detail": "The page you're looking for doesn't exist."},
        status_code=404,
    )


@app.on_event("startup")
async def on_startup():
    """Initialize database and verify environment on server start."""
    await init_db(migration_version=3)

    # Check for ffmpeg (soft warning — degraded mode without it)
    # This is expanded in Checkpoint 2
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        print(
            "WARNING: ffmpeg not found. Install with: sudo apt install ffmpeg. "
            "Thumbnails will not be generated."
        )


@app.get("/health")
async def health():
    return {"status": "ok"}
