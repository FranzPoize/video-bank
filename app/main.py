"""
FastAPI application entry point.

Creates the app, mounts static directories, initializes the database,
and includes all route modules.
"""

import logging
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

# ── Logging constants ──────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", str(_project_root / "logs"))
LOG_FILE = os.path.join(LOG_DIR, "video-bank.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# ───────────────────────────────────────────────────────────────────

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

# Mount static files (JS, CSS) at /static
static_dir = _project_root / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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
    """Initialize database, configure logging, and verify environment."""

    # ── Configure file-based logging (skip in test environment) ──
    if "PYTEST_CURRENT_TEST" not in os.environ:
        os.makedirs(LOG_DIR, exist_ok=True)
        logging.basicConfig(
            filename=LOG_FILE,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
            force=True,
        )
    # ─────────────────────────────────────────────────────────────

    await init_db(migration_version=4)

    # Check for ffmpeg (required for clip creation)
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        logging.warning(
            "ffmpeg not found. Install with: sudo apt install ffmpeg. "
            "Thumbnails will not be generated."
        )
    else:
        logging.info("ffmpeg found at %s", ffmpeg_path)

    db_path = os.environ.get("DATABASE_PATH", str(_project_root / "data" / "video_bank.db"))
    logging.info(
        "Video Bank started. DB path: %s, LOG_DIR: %s",
        db_path, LOG_DIR,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
