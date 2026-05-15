"""
FastAPI application entry point.

Creates the app, mounts static directories, initializes the database,
and includes all route modules.
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── Logging constants ──────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
LOG_FILE = os.path.join(LOG_DIR, "video-bank.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# ───────────────────────────────────────────────────────────────────

from app.database import init_db
from app.routes.videos import router as videos_router
from app.routes.tags import router as tags_router
from app.templates import (
    templates,
    get_i18n_context,
    parse_accept_language,
    DEFAULT_LANG,
)

_project_root = Path(__file__).resolve().parent.parent

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


# ── Language detection middleware ──────────────────────────────────
@app.middleware("http")
async def language_middleware(request: Request, call_next):
    """Detect user language and store in request.state.

    Priority:
    1. `lang` cookie (highest)
    2. Accept-Language header
    3. Default: "en"
    """
    # Check for lang cookie
    lang = request.cookies.get("lang")

    # Fall back to Accept-Language header
    if lang is None:
        accept_lang = request.headers.get("accept-language")
        lang = parse_accept_language(accept_lang)

    # Default to English
    if lang is None:
        lang = DEFAULT_LANG

    # Store in request.state for use in routes
    request.state.current_lang = lang
    request.state.i18n = get_i18n_context(lang)

    response = await call_next(request)
    return response


# ── Exception handlers with i18n ──────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc):
    """Return a styled error page for HTTP errors."""
    # Get i18n context from request.state (set by middleware)
    i18n = getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))

    return templates.TemplateResponse(
        request, "error.html",
        {
            **i18n,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Override 404 with a custom template."""
    i18n = getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
    _ = i18n["_"]

    return templates.TemplateResponse(
        request, "error.html",
        {
            **i18n,
            "status_code": 404,
            "detail": _("error.page_not_found"),
        },
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
