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

# Ensure the project root is on sys.path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.database import init_db
from app.routes.videos import router as videos_router

app = FastAPI(title="Video Bank")

# Mount static directories for uploaded files
uploads_dir = _project_root / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "videos").mkdir(parents=True, exist_ok=True)
(uploads_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Include routers
app.include_router(videos_router)


@app.on_event("startup")
async def on_startup():
    """Initialize database and verify environment on server start."""
    await init_db(migration_version=1)

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
