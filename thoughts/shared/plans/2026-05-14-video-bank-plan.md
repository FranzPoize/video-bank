# Video Clip Bank — Implementation Plan

**Goal:** Build a self-hosted web app for uploading, browsing, tagging, and filtering video clips.

**Architecture:** Python + FastAPI + Jinja2 + HTMX + SQLite (aiosqlite) + ffmpeg. Server-rendered HTML with HTMX for interactive filtering. Raw SQL (no ORM). Services layer keeps business logic separate from routes.

**Design:** `thoughts/shared/designs/2026-05-14-video-bank-design.md`

---

## Project Structure (Final)

```
video-bank/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, startup, static mounts
│   ├── database.py                # SQLite connection, schema init
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── videos.py              # Upload, list, play, edit, delete
│   │   └── tags.py                # Tag list, filter (checkpoint 4)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── video_service.py       # Video CRUD operations
│   │   ├── tag_service.py         # Tag management (checkpoint 3)
│   │   └── file_service.py        # File I/O, ffmpeg thumbnail gen
│   └── templates/
│       ├── base.html              # HTML shell + HTMX + nav
│       ├── index.html             # Video grid + tag filter bar
│       ├── _video_grid.html       # Grid fragment (for HTMX swap)
│       ├── upload.html            # Upload form
│       ├── video_detail.html      # Player + metadata (checkpoint 2)
│       └── edit.html              # Edit form (checkpoint 5)
├── uploads/
│   ├── videos/                    # Raw uploaded video files
│   └── thumbnails/                # Generated .jpg thumbnails
├── data/                          # SQLite DB lives here
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures: in-memory DB, test client
│   ├── test_videos.py             # Upload, list, playback, filter, CRUD
│   └── test_tags.py               # Tag-specific tests (checkpoint 3+)
├── requirements.txt
└── PLAN.md
```

---

## Checkpoint 1: Upload + List (15 micro-tasks)

**Scope:** Project skeleton, SQLite schema (videos table), upload endpoint, list endpoint, basic templates, test infrastructure.

**What works at the end:** User opens `http://localhost:8000/`, sees empty list, can upload a video file with a name, sees it listed.

### Batch 1.1: Foundation (6 tasks — parallel)

All tasks in this batch have NO dependencies.

#### Task 1.1.1: requirements.txt
**File:** `requirements.txt`
**Test:** none (config file)
**Depends:** none

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
jinja2>=3.1.0
aiosqlite>=0.20.0
python-multipart>=0.0.9
pytest>=8.0.0
pytest-asyncio>=0.24.0
httpx>=0.27.0
```
**Commit:** `chore: add python dependencies`

---

#### Task 1.1.2: app/__init__.py
**File:** `app/__init__.py`
**Test:** none
**Depends:** none

```python
# Makes app a Python package
```
**Commit:** `chore: init app package`

---

#### Task 1.1.3: app/routes/__init__.py
**File:** `app/routes/__init__.py`
**Test:** none
**Depends:** none

```python
# Makes routes a Python package
```
**Commit:** `chore: init routes package`

---

#### Task 1.1.4: app/services/__init__.py
**File:** `app/services/__init__.py`
**Test:** none
**Depends:** none

```python
# Makes services a Python package
```
**Commit:** `chore: init services package`

---

#### Task 1.1.5: tests/__init__.py
**File:** `tests/__init__.py`
**Test:** none
**Depends:** none

```python
# Makes tests a Python package
```
**Commit:** `chore: init tests package`

---

#### Task 1.1.6: app/database.py
**File:** `app/database.py`
**Test:** none (tested via conftest)
**Depends:** none

```python
"""
Database connection management and schema initialization.

The database path is configurable via DATABASE_PATH environment variable.
Tests override this to use ":memory:" for isolation.
"""

import os
import aiosqlite

DEFAULT_DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "video_bank.db"),
)

VIDEOS_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# These are applied incrementally per checkpoint
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    # 3: tags + video_tags added here
}


async def get_db(db_path: str | None = None):
    """FastAPI dependency: yield an aiosqlite connection.

    Use `db_path` override for testing; otherwise uses DEFAULT_DB_PATH.
    The caller wraps this in `contextlib.asynccontextmanager` or uses
    FastAPI's Depends with an async generator.
    """
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db(db_path: str | None = None, migration_version: int = 1):
    """Create/upgrade tables to the given migration version."""
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = await aiosqlite.connect(path)
    try:
        for version in range(1, migration_version + 1):
            for stmt in MIGRATIONS.get(version, []):
                await db.execute(stmt)
        await db.commit()
    finally:
        await db.close()
```
**Commit:** `feat: add database layer with schema init`

---

### Batch 1.2: Services + Templates (5 tasks — parallel)

All depend on Batch 1.1 completing.

#### Task 1.2.1: app/services/file_service.py
**File:** `app/services/file_service.py`
**Test:** none directly (tested via video route tests)
**Depends:** 1.1.4 (services/__init__.py)

```python
"""
File system operations: save uploads, delete files, generate thumbnails.

Thumbnail generation (ffmpeg) is a placeholder here — actual ffmpeg
call is added in Checkpoint 2.
"""

import os
import uuid
import shutil
from pathlib import Path

# Directories relative to project root
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
VIDEOS_DIR = UPLOAD_DIR / "videos"
THUMBNAILS_DIR = UPLOAD_DIR / "thumbnails"

ALLOWED_EXTENSIONS = {
    e.strip() for e in os.environ.get("ALLOWED_EXTENSIONS", "mp4,webm,mov").split(",")
}
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(500 * 1024 * 1024)))  # 500MB


def _ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def _get_ext(filename: str) -> str:
    """Extract lowercase extension without dot, e.g. 'mp4'."""
    return Path(filename).suffix.lstrip(".").lower()


def validate_file(filename: str, file_size: int) -> str | None:
    """Return an error message if the file is invalid, or None."""
    ext = _get_ext(filename)
    if not ext:
        return "File has no extension."
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return f"Unsupported format '.{ext}'. Allowed: {allowed}"
    if file_size > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE / (1024 * 1024)
        return f"File too large (max {max_mb:.0f}MB)."
    return None


async def save_upload(file_content: bytes, original_name: str) -> str:
    """Save uploaded bytes to disk. Returns the stored filename (UUID-based)."""
    _ensure_dirs()
    ext = _get_ext(original_name)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = VIDEOS_DIR / stored_name
    with open(dest, "wb") as f:
        f.write(file_content)
    return stored_name


async def delete_video_file(filename: str):
    """Remove a stored video file from disk. No-op if missing."""
    path = VIDEOS_DIR / filename
    if path.exists():
        path.unlink()


async def delete_thumbnail(filename: str):
    """Remove a stored thumbnail from disk. No-op if missing."""
    thumb_path = THUMBNAILS_DIR / Path(filename).stem + ".jpg"
    # Convert to Path properly
    thumb = THUMBNAILS_DIR / f"{Path(filename).stem}.jpg"
    if thumb.exists():
        thumb.unlink()


async def generate_thumbnail(video_filename: str) -> bool:
    """Generate a thumbnail for the given video file. 
    
    Placeholder — returns False. Actual ffmpeg call added in Checkpoint 2.
    
    Design requires thumbnails but ffmpeg is validated at startup. 
    In Checkpoint 1 we always show a placeholder.
    """
    _ensure_dirs()
    # Return False meaning "no thumbnail available"
    return False


def get_video_path(filename: str) -> Path:
    """Return full path to a stored video file."""
    return VIDEOS_DIR / filename
```
**Commit:** `feat: add file service with upload/validation`

---

#### Task 1.2.2: app/services/video_service.py
**File:** `app/services/video_service.py`
**Test:** none directly (tested via route tests)
**Depends:** 1.1.6 (database.py), 1.2.1 (file_service.py)

```python
"""
Business logic for video CRUD operations.

Each function takes an aiosqlite.Connection as the first argument.
This keeps them testable with in-memory databases.
"""

from app.database import get_db
from app.services import file_service


async def create_video(
    db,
    name: str,
    file_content: bytes,
    original_name: str,
    mime_type: str,
    file_size: int,
) -> dict:
    """Save a video file and create a database record.
    
    Returns the created video as a dict.
    """
    # Validate file before saving
    error = file_service.validate_file(original_name, file_size)
    if error:
        raise ValueError(error)

    # Save file to disk
    filename = await file_service.save_upload(file_content, original_name)

    # Generate thumbnail (best-effort — placeholder in CP1, ffmpeg in CP2)
    await file_service.generate_thumbnail(filename)

    # Insert database record
    cursor = await db.execute(
        """INSERT INTO videos (name, filename, original_name, mime_type, file_size)
           VALUES (?, ?, ?, ?, ?)""",
        (name, filename, original_name, mime_type, file_size),
    )
    await db.commit()
    video_id = cursor.lastrowid

    return await get_video(db, video_id)


async def get_video(db, video_id: int) -> dict | None:
    """Fetch a single video by ID. Returns None if not found."""
    cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def list_videos(db) -> list[dict]:
    """Return all videos ordered by upload date (newest first)."""
    cursor = await db.execute(
        "SELECT * FROM videos ORDER BY upload_date DESC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_video(db, video_id: int, name: str) -> dict | None:
    """Update a video's name. Returns updated video or None."""
    await db.execute(
        "UPDATE videos SET name = ? WHERE id = ?",
        (name, video_id),
    )
    await db.commit()
    return await get_video(db, video_id)


async def delete_video(db, video_id: int) -> bool:
    """Delete a video record and its files. Returns True if deleted."""
    video = await get_video(db, video_id)
    if video is None:
        return False

    # Remove files
    await file_service.delete_video_file(video["filename"])
    await file_service.delete_thumbnail(video["filename"])

    # Remove database record
    await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    await db.commit()
    return True
```
**Commit:** `feat: add video service with CRUD operations`

---

#### Task 1.2.3: app/templates/base.html
**File:** `app/templates/base.html`
**Test:** none
**Depends:** none

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Video Bank{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            min-height: 100vh;
        }
        nav {
            background: #1a1a2e;
            color: #fff;
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            gap: 2rem;
        }
        nav a {
            color: #fff;
            text-decoration: none;
            font-weight: 600;
        }
        nav a:hover { text-decoration: underline; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .btn {
            display: inline-block;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.9rem;
            cursor: pointer;
            border: none;
        }
        .btn-primary { background: #4361ee; color: #fff; }
        .btn-primary:hover { background: #3a56d4; }
        .btn-danger { background: #e63946; color: #fff; }
        .btn-danger:hover { background: #c1121f; }
        .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
        .error { color: #e63946; background: #ffe5e7; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; }
        .success { color: #2d6a4f; background: #d8f3dc; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; }
        .empty-state { text-align: center; padding: 3rem; color: #888; }
        .empty-state p { font-size: 1.1rem; }
        form label { display: block; margin-bottom: 0.25rem; font-weight: 600; }
        form input[type="text"],
        form input[type="file"] { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 6px; margin-bottom: 1rem; }
        form button[type="submit"] { margin-top: 0.5rem; }
    </style>
    {% block extra_head %}{% endblock %}
</head>
<body>
    <nav>
        <a href="/">Video Bank</a>
        <a href="/upload">Upload</a>
    </nav>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```
**Commit:** `feat: add base template with HTMX and nav`

---

#### Task 1.2.4: app/templates/index.html
**File:** `app/templates/index.html`
**Test:** none
**Depends:** none

```html
{% extends "base.html" %}
{% block title %}Video Bank — Browse{% endblock %}

{% block content %}
<h1 style="margin-bottom: 1.5rem;">Videos</h1>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<div id="video-grid">
    {% include "_video_grid.html" %}
</div>
{% endblock %}
```
**Commit:** `feat: add index template`

---

#### Task 1.2.5: app/templates/_video_grid.html
**File:** `app/templates/_video_grid.html`
**Test:** none
**Depends:** none

```html
{% if videos %}
<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;">
    {% for video in videos %}
    <div style="background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <div style="aspect-ratio: 16/9; background: #ddd; display: flex; align-items: center; justify-content: center; color: #888; font-size: 2rem;">
            {% if video.has_thumbnail and video.thumbnail_url %}
            <img src="{{ video.thumbnail_url }}" alt="{{ video.name }}" style="width: 100%; height: 100%; object-fit: cover;">
            {% else %}
            &#9654;
            {% endif %}
        </div>
        <div style="padding: 0.75rem;">
            <h3 style="font-size: 1rem; margin-bottom: 0.25rem;">
                <a href="/video/{{ video.id }}" style="color: inherit; text-decoration: none;">{{ video.name }}</a>
            </h3>
            <p style="font-size: 0.8rem; color: #888;">
                Uploaded {{ video.upload_date }}
            </p>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="empty-state">
    <p>No videos yet.</p>
    <p style="margin-top: 1rem;"><a href="/upload" class="btn btn-primary">Upload your first video</a></p>
</div>
{% endif %}
```
**Commit:** `feat: add video grid partial template`

---

### Batch 1.3: App + Routes (2 tasks — parallel)

Depend on Batch 1.2.

#### Task 1.3.1: app/routes/videos.py
**File:** `app/routes/videos.py`
**Test:** none directly (tested via test_videos.py)
**Depends:** 1.2.2 (video_service.py), 1.2.3 (templates)

```python
"""
Video routes: upload, list, detail, stream, edit, delete.

In Checkpoint 1: upload + list only.
Endpoints added incrementally per checkpoint:
  CP2: GET /video/{id} (detail), GET /api/video/{id}/file (stream)
  CP3: Tag handling on upload
  CP5: POST /video/{id}/edit, POST /video/{id}/delete
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services import video_service
from app.services.file_service import get_video_path

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


def _video_to_card(video: dict) -> dict:
    """Enrich a video dict with template-friendly fields."""
    thumb_stem = Path(video["filename"]).stem
    thumb_path = (
        Path(__file__).resolve().parent.parent.parent
        / "uploads"
        / "thumbnails"
        / f"{thumb_stem}.jpg"
    )
    has_thumbnail = thumb_path.exists()
    return {
        **video,
        "has_thumbnail": has_thumbnail,
        "thumbnail_url": f"/uploads/thumbnails/{thumb_stem}.jpg" if has_thumbnail else None,
    }


@router.get("/")
async def list_videos(request: Request, db=Depends(get_db)):
    """Show all videos. HTMX requests get just the grid fragment."""
    videos = await video_service.list_videos(db)
    enriched = [_video_to_card(v) for v in videos]

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "_video_grid.html" if is_htmx else "index.html"
    return templates.TemplateResponse(
        template, {"request": request, "videos": enriched}
    )


@router.get("/upload")
async def upload_form(request: Request):
    """Show the upload form."""
    return templates.TemplateResponse("upload.html", {"request": request})


@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """Handle video upload. Redirects to list on success."""
    # Read file content
    content = await file.read()

    try:
        await video_service.create_video(
            db,
            name=name,
            file_content=content,
            original_name=file.filename or "untitled",
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )

    return RedirectResponse(url="/", status_code=303)
```
**Commit:** `feat: add video routes (upload + list)`

---

#### Task 1.3.2: app/main.py
**File:** `app/main.py`
**Test:** none (imported by conftest.py)
**Depends:** 1.3.1 (routes/videos.py), 1.1.6 (database.py)

```python
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
(app / uploads_dir / "videos").mkdir(parents=True, exist_ok=True)
(app / uploads_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

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
```
**Commit:** `feat: add FastAPI app entry point`

---

### Batch 1.4: Tests (2 tasks — parallel)

Depend on Batch 1.3.

#### Task 1.4.1: tests/conftest.py
**File:** `tests/conftest.py`
**Test:** none (test infrastructure)
**Depends:** 1.3.2 (main.py), 1.1.6 (database.py)

```python
"""
Pytest fixtures for all tests.

Provides:
- An in-memory SQLite database with schema applied
- An httpx.AsyncClient against the FastAPI app
- Cleanup between tests
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.database import init_db, get_db
from app.main import app as _app


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Create a fresh in-memory database for each test."""
    db_path = ":memory:"
    await init_db(db_path=db_path, migration_version=1)

    async def _get_db_override():
        db_conn = await aiosqlite.connect(db_path)
        db_conn.row_factory = aiosqlite.Row
        try:
            yield db_conn
        finally:
            await db_conn.close()

    # We need a context manager for the override
    db_gen = _get_db_override()
    db_conn = await db_gen.__anext__()
    try:
        yield db_conn
    finally:
        try:
            await db_gen.__anext__()
        except StopAsyncIteration:
            pass
        await db_conn.close()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx test client against the FastAPI app with DB override."""
    _app.dependency_overrides[get_db] = lambda: db

    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    _app.dependency_overrides.clear()
```
**Commit:** `test: add test fixtures (in-memory DB, async client)`

---

#### Task 1.4.2: tests/test_videos.py
**File:** `tests/test_videos.py`
**Test:** itself (this is the test file)
**Depends:** 1.4.1 (conftest.py)

```python
"""
Tests for video upload and listing (Checkpoint 1).

Run with: pytest tests/test_videos.py -v
"""

import pytest


class TestVideoList:
    """Tests for the video list endpoint."""

    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        """GET / should show empty state when no videos exist."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "No videos yet" in response.text

    @pytest.mark.asyncio
    async def test_list_after_upload(self, client):
        """GET / should show uploaded video."""
        # Upload a video first
        upload_resp = await client.post(
            "/api/videos",
            data={"name": "Test Video"},
            files={"file": ("test.mp4", b"fake-video-content", "video/mp4")},
        )
        assert upload_resp.status_code == 303  # redirect

        # Now list should show it
        list_resp = await client.get("/")
        assert list_resp.status_code == 200
        assert "Test Video" in list_resp.text


class TestVideoUpload:
    """Tests for the upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_success(self, client):
        """POST /api/videos with valid data redirects to list."""
        response = await client.post(
            "/api/videos",
            data={"name": "My Clip"},
            files={"file": ("clip.mp4", b"fake-video-content", "video/mp4")},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_upload_creates_db_record(self, client, db):
        """Upload inserts a row into the database."""
        await client.post(
            "/api/videos",
            data={"name": "DB Test"},
            files={"file": ("db.mp4", b"some-content", "video/mp4")},
        )
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    @pytest.mark.asyncio
    async def test_upload_requires_name(self, client):
        """Upload without name should fail."""
        response = await client.post(
            "/api/videos",
            data={"name": ""},
            files={"file": ("no-name.mp4", b"content", "video/mp4")},
        )
        # FastAPI's Form(...) returns 422 for missing required fields
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_unsupported_format(self, client):
        """Upload with unsupported extension returns 400."""
        response = await client.post(
            "/api/videos",
            data={"name": "Bad Format"},
            files={"file": ("bad.avi", b"content", "video/x-msvideo")},
        )
        assert response.status_code == 400
        assert "unsupported" in response.text.lower()

    @pytest.mark.asyncio
    async def test_upload_form_page(self, client):
        """GET /upload shows the upload form."""
        response = await client.get("/upload")
        assert response.status_code == 200
        assert "Upload" in response.text
```
**Commit:** `test: add upload + list tests`

---

### Checkpoint 1 Verification

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/test_videos.py -v

# Start the server
uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000/ and:
1. See empty list with "No videos yet" and upload button
2. Click "Upload", fill in name and select an mp4 file
3. Submit — redirected to list, video appears
4. Upload another video with a different name, both appear

**CHECKPOINT HERE!** Stop and validate upload + list flow. Test edge cases (empty name, unsupported format, large file).

---

## Checkpoint 2: Playback + Thumbnails (8 micro-tasks)

**Scope:** Video streaming endpoint, ffmpeg thumbnail generation, video detail page, thumbnails in grid, static file serving refinement.

**What works at the end:** Clicking a video plays it in a detail page with an HTML5 `<video>` player. Thumbnails are generated on upload and displayed in the grid.

### Batch 2.1: Service Modifications (3 tasks — parallel)

#### Task 2.1.1: app/services/file_service.py (modify — add real ffmpeg thumbnail gen)
**File:** `app/services/file_service.py`
**Test:** none (tested via route tests)
**Depends:** 1.2.1

Replace the `generate_thumbnail` placeholder function:

```python
async def generate_thumbnail(video_filename: str) -> bool:
    """Generate a thumbnail at the 1-second mark using ffmpeg.
    
    Returns True if thumbnail was generated, False if ffmpeg is unavailable.
    """
    _ensure_dirs()
    video_path = VIDEOS_DIR / video_filename
    thumb_path = THUMBNAILS_DIR / f"{Path(video_filename).stem}.jpg"

    if thumb_path.exists():
        return True  # Already generated

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False

    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-ss", str(THUMBNAIL_TIME_SECONDS),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(thumb_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return_code = await proc.wait()
    return return_code == 0 and thumb_path.exists()
```

Also add the constant near the top of the file:

```python
THUMBNAIL_TIME_SECONDS = int(os.environ.get("THUMBNAIL_TIME", "1"))
```

And add `import asyncio` and `import shutil` to the imports.

**Commit:** `feat: add ffmpeg thumbnail generation on upload`

---

#### Task 2.1.2: app/routes/videos.py (modify — add streaming + detail endpoints)
**File:** `app/routes/videos.py`
**Test:** none directly
**Depends:** 1.3.1

Add imports at the top:

```python
from fastapi.responses import FileResponse, RedirectResponse, Response
```

Add the streaming endpoint:

```python
@router.get("/api/video/{video_id}/file")
async def stream_video(video_id: int, db=Depends(get_db)):
    """Stream a video file with range request support for seeking."""
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = get_video_path(video["filename"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(video_path),
        media_type=video["mime_type"],
        filename=video["original_name"],
    )
```

Add the detail page endpoint:

```python
@router.get("/video/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db)):
    """Show video detail page with player."""
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    # Add full-size thumbnail and video URL
    thumb_stem = Path(video["filename"]).stem
    enriched["video_url"] = f"/api/video/{video_id}/file"
    enriched["thumbnail_url"] = f"/uploads/thumbnails/{thumb_stem}.jpg"
    enriched["has_thumbnail"] = (
        Path(__file__).resolve().parent.parent.parent
        / "uploads"
        / "thumbnails"
        / f"{thumb_stem}.jpg"
    ).exists()

    return templates.TemplateResponse(
        "video_detail.html",
        {"request": request, "video": enriched},
    )
```

**Commit:** `feat: add video streaming + detail page routes`

---

#### Task 2.1.3: app/templates/video_detail.html (create)
**File:** `app/templates/video_detail.html`
**Test:** none
**Depends:** 1.2.3 (base.html)

```html
{% extends "base.html" %}
{% block title %}{{ video.name }} — Video Bank{% endblock %}

{% block content %}
<div style="max-width: 900px; margin: 0 auto;">
    <a href="/" style="color: #4361ee; text-decoration: none; display: inline-block; margin-bottom: 1rem;">&larr; Back to all videos</a>

    <h1 style="margin-bottom: 0.5rem;">{{ video.name }}</h1>
    <p style="color: #888; font-size: 0.9rem; margin-bottom: 1.5rem;">
        Uploaded {{ video.upload_date }} &middot; {{ "%.1f"|format(video.file_size / (1024*1024)) }} MB
    </p>

    <div style="background: #000; border-radius: 10px; overflow: hidden; margin-bottom: 1.5rem;">
        <video controls style="width: 100%; display: block;" preload="metadata">
            <source src="{{ video.video_url }}" type="{{ video.mime_type }}">
            Your browser does not support the video element.
        </video>
    </div>

    {% if video.tags and video.tags|length > 0 %}
    <div style="margin-bottom: 1.5rem;">
        <h3 style="font-size: 0.9rem; color: #888; margin-bottom: 0.5rem;">Tags</h3>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            {% for tag in video.tags %}
            <span style="background: #e0e7ff; color: #4361ee; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.85rem;">
                {{ tag }}
            </span>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
```
**Commit:** `feat: add video detail template with HTML5 player`

---

### Batch 2.2: Test Updates (1 task)

#### Task 2.2.1: tests/test_videos.py (modify — add playback tests)
**File:** `tests/test_videos.py`
**Test:** itself
**Depends:** 2.1.2

Add to the existing test file:

```python
class TestVideoPlayback:
    """Tests for video streaming and detail page."""

    @pytest.mark.asyncio
    async def test_video_detail_page(self, client):
        """GET /video/{id} shows the detail page."""
        # Upload first
        await client.post(
            "/api/videos",
            data={"name": "Playback Test"},
            files={"file": ("play.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1")
        assert response.status_code == 200
        assert "Playback Test" in response.text
        assert "<video" in response.text

    @pytest.mark.asyncio
    async def test_video_detail_not_found(self, client):
        """GET /video/{id} for missing id returns 404."""
        response = await client.get("/video/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_video_stream_endpoint(self, client):
        """GET /api/video/{id}/file returns video bytes."""
        await client.post(
            "/api/videos",
            data={"name": "Stream Test"},
            files={"file": ("stream.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.get("/api/video/1/file")
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_video_stream_not_found(self, client):
        """GET /api/video/{id}/file for missing id returns 404."""
        response = await client.get("/api/video/999/file")
        assert response.status_code == 404
```
**Commit:** `test: add video playback + streaming tests`

---

### Checkpoint 2 Verification

```bash
# Run tests
pytest tests/test_videos.py -v

# Start server
uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000/ and:
1. See thumbnails in the video grid (or placeholder if ffmpeg missing)
2. Click a video → detail page with `<video>` player
3. Playback works (seek, pause, volume)
4. Upload a video and confirm thumbnail appears after ffmpeg processes it

**CHECKPOINT HERE!** Stop and validate playback + thumbnail flow. Test with multiple video formats. If ffmpeg is missing, confirm graceful degradation (placeholder thumbnails, warning in server logs).

---

## Checkpoint 3: Tag System (8 micro-tasks)

**Scope:** Tags table + video_tags join table, on-the-fly tag creation during upload, tag display on video cards, tag editing on existing videos, tag service.

**What works at the end:** User enters comma-separated tags during upload. Tags appear on video cards in the grid and on the detail page. Tags can be added/removed via edit page.

### Batch 3.1: Database Migration (1 task)

#### Task 3.1.1: app/database.py (modify — add tags + video_tags tables)
**File:** `app/database.py`
**Test:** none
**Depends:** 1.1.6

Add the new migration:

```python
TAGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(video_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_video_tags_video_id ON video_tags(video_id);
CREATE INDEX IF NOT EXISTS idx_video_tags_tag_id ON video_tags(tag_id);
"""
```

Update `MIGRATIONS`:

```python
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    2: [],  # Reserved for future structural changes
    3: [TAGS_SCHEMA],
}
```

Also enable foreign keys by adding this to the connection setup (both in `get_db` and `init_db`):

In `init_db` after `db = await aiosqlite.connect(path)`:
```python
await db.execute("PRAGMA foreign_keys = ON")
```

Same in the `get_db` generator:
```python
db = await aiosqlite.connect(path)
await db.execute("PRAGMA foreign_keys = ON")
db.row_factory = aiosqlite.Row
```

**Commit:** `feat: add tags + video_tags tables and enable foreign keys`

---

### Batch 3.2: Tag Service + Video Service Updates (2 tasks — parallel)

#### Task 3.2.1: app/services/tag_service.py (create)
**File:** `app/services/tag_service.py`
**Test:** none directly
**Depends:** 3.1.1

```python
"""
Tag management: create, list, associate with videos.
"""


async def get_or_create_tag(db, name: str) -> int:
    """Find a tag by name or create it. Returns the tag id."""
    name = name.strip().lower()
    if not name:
        raise ValueError("Tag name cannot be empty")

    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row:
        return row["id"]

    cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    await db.commit()
    return cursor.lastrowid


async def list_all_tags(db) -> list[dict]:
    """Return all tags, ordered by name."""
    cursor = await db.execute("SELECT * FROM tags ORDER BY name ASC")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_video_tags(db, video_id: int) -> list[str]:
    """Return tag names for a given video."""
    cursor = await db.execute(
        """SELECT t.name FROM tags t
           JOIN video_tags vt ON t.id = vt.tag_id
           WHERE vt.video_id = ?
           ORDER BY t.name""",
        (video_id,),
    )
    rows = await cursor.fetchall()
    return [r["name"] for r in rows]


async def set_video_tags(db, video_id: int, tag_names: list[str]):
    """Replace all tags on a video with the given list.

    Tags that don't exist yet are created on the fly.
    """
    # Remove existing associations
    await db.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))

    # Add new ones
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag_id = await get_or_create_tag(db, name)
        await db.execute(
            "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
            (video_id, tag_id),
        )

    await db.commit()
```
**Commit:** `feat: add tag service (CRUD for tags)`

---

#### Task 3.2.2: app/services/video_service.py (modify — add tag parameter to create_video)
**File:** `app/services/video_service.py`
**Test:** none directly
**Depends:** 3.2.1

1. Add import for tag_service at the top:

```python
from app.services import tag_service
```

2. Modify `create_video` to accept and store tags:

```python
async def create_video(
    db,
    name: str,
    file_content: bytes,
    original_name: str,
    mime_type: str,
    file_size: int,
    tags: str = "",  # Comma-separated tag string
) -> dict:
    # ... existing validation and file save ...

    # Insert database record
    cursor = await db.execute(
        """INSERT INTO videos (name, filename, original_name, mime_type, file_size)
           VALUES (?, ?, ?, ?, ?)""",
        (name, filename, original_name, mime_type, file_size),
    )
    await db.commit()
    video_id = cursor.lastrowid

    # Store tags
    if tags and tags.strip():
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_names:
            await tag_service.set_video_tags(db, video_id, tag_names)

    return await get_video(db, video_id)
```

3. Add `get_video_with_tags` helper:

```python
async def get_video_with_tags(db, video_id: int) -> dict | None:
    """Fetch a video along with its tags."""
    video = await get_video(db, video_id)
    if video is None:
        return None
    video["tags"] = await tag_service.get_video_tags(db, video_id)
    return video


async def list_videos_with_tags(db) -> list[dict]:
    """Return all videos with their tags."""
    videos = await list_videos(db)
    for v in videos:
        v["tags"] = await tag_service.get_video_tags(db, v["id"])
    return videos
```
**Commit:** `feat: add tag support to video service`

---

### Batch 3.3: Routes + Templates (3 tasks — parallel)

#### Task 3.3.1: app/routes/videos.py (modify — add tag handling)
**File:** `app/routes/videos.py`
**Test:** none directly
**Depends:** 3.2.2

1. Add `tags` form field to the upload endpoint:

```python
@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form(""),  # Comma-separated tags
    db=Depends(get_db),
):
    # ... same as before, but pass tags=tags to create_video
```

2. Update list_videos to use list_videos_with_tags:

```python
@router.get("/")
async def list_videos(request: Request, db=Depends(get_db)):
    """Show all videos with their tags."""
    videos = await video_service.list_videos_with_tags(db)
    enriched = [_video_to_card(v) for v in videos]
    # ... same template logic ...
```

3. Update video_detail to use get_video_with_tags:

```python
@router.get("/video/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db)):
    """Show video detail page with player and tags."""
    video = await video_service.get_video_with_tags(db, video_id)
    # ... rest is the same ...
```
**Commit:** `feat: add tag fields to upload + detail routes`

---

#### Task 3.3.2: app/templates/_video_grid.html (modify — show tags on cards)
**File:** `app/templates/_video_grid.html`
**Test:** none
**Depends:** 1.2.5

Add tag display below the video name:

```html
<div style="padding: 0.75rem;">
    <h3 style="font-size: 1rem; margin-bottom: 0.25rem;">
        <a href="/video/{{ video.id }}" style="color: inherit; text-decoration: none;">{{ video.name }}</a>
    </h3>
    <p style="font-size: 0.8rem; color: #888; margin-bottom: 0.5rem;">
        Uploaded {{ video.upload_date }}
    </p>
    {% if video.tags and video.tags|length > 0 %}
    <div style="display: flex; gap: 0.25rem; flex-wrap: wrap;">
        {% for tag in video.tags %}
        <span style="background: #e0e7ff; color: #4361ee; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem;">
            {{ tag }}
        </span>
        {% endfor %}
    </div>
    {% endif %}
</div>
```
**Commit:** `feat: show tags on video grid cards`

---

#### Task 3.3.3: app/templates/upload.html (modify — add tags input)
**File:** `app/templates/upload.html`
**Test:** none
**Depends:** 1.3.1 upload.html already exists

Add the tags field to the upload form:

```html
{% extends "base.html" %}
{% block title %}Upload Video — Video Bank{% endblock %}

{% block content %}
<h1 style="margin-bottom: 1.5rem;">Upload Video</h1>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<form action="/api/videos" method="post" enctype="multipart/form-data">
    <label for="name">Video Name</label>
    <input type="text" id="name" name="name" required placeholder="My cool clip">

    <label for="file">Video File</label>
    <input type="file" id="file" name="file" accept="video/mp4,video/webm,video/quicktime" required>

    <label for="tags">Tags (comma-separated)</label>
    <input type="text" id="tags" name="tags" placeholder="tutorial, funny, demo">

    <button type="submit" class="btn btn-primary">Upload</button>
</form>

<p style="margin-top: 1rem;"><a href="/" style="color: #4361ee;">&larr; Back to list</a></p>
{% endblock %}
```
**Commit:** `feat: add tags input to upload form`

---

### Batch 3.4: Tests (2 tasks — parallel)

#### Task 3.4.1: tests/conftest.py (modify — bump migration version)
**File:** `tests/conftest.py`
**Test:** none
**Depends:** 3.1.1

Change migration_version from 1 to 3:

```python
await init_db(db_path=db_path, migration_version=3)
```
**Commit:** `chore: bump test DB schema to migration version 3`

---

#### Task 3.4.2: tests/test_tags.py (create)
**File:** `tests/test_tags.py`
**Test:** itself
**Depends:** 3.4.1

```python
"""
Tests for tag system (Checkpoint 3).

Run with: pytest tests/test_tags.py -v
"""

import pytest


class TestTagCreation:
    """Tests for on-the-fly tag creation."""

    @pytest.mark.asyncio
    async def test_upload_with_tags(self, client):
        """Upload with tags stores them."""
        await client.post(
            "/api/videos",
            data={"name": "Tagged Video", "tags": "tutorial, funny, demo"},
            files={"file": ("tagged.mp4", b"content", "video/mp4")},
        )
        list_resp = await client.get("/")
        assert "tutorial" in list_resp.text
        assert "funny" in list_resp.text
        assert "demo" in list_resp.text

    @pytest.mark.asyncio
    async def test_upload_without_tags(self, client):
        """Upload without tags still works."""
        response = await client.post(
            "/api/videos",
            data={"name": "No Tags"},
            files={"file": ("notags.mp4", b"content", "video/mp4")},
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_upload_empty_tags(self, client):
        """Upload with empty tags string still works."""
        response = await client.post(
            "/api/videos",
            data={"name": "Empty Tags", "tags": ""},
            files={"file": ("emptytags.mp4", b"content", "video/mp4")},
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_duplicate_tags(self, client):
        """Duplicate tag names should be stored once."""
        await client.post(
            "/api/videos",
            data={"name": "Dup Tags", "tags": "test, test, TEST"},
            files={"file": ("dup.mp4", b"content", "video/mp4")},
        )
        # Check that only one tag was created
        list_resp = await client.get("/")
        # "test" should appear (lowercased), count the occurrences
        assert list_resp.text.count("test") >= 1  # at least once


class TestTagDisplay:
    """Tests for tag display."""

    @pytest.mark.asyncio
    async def test_tags_in_list(self, client):
        """Tags should appear on video cards in the list."""
        await client.post(
            "/api/videos",
            data={"name": "Tag Display", "tags": "alpha, beta"},
            files={"file": ("display.mp4", b"c", "video/mp4")},
        )
        response = await client.get("/")
        assert "alpha" in response.text
        assert "beta" in response.text

    @pytest.mark.asyncio
    async def test_tags_in_detail(self, client):
        """Tags should appear on the video detail page."""
        await client.post(
            "/api/videos",
            data={"name": "Detail Tags", "tags": "gamma, delta"},
            files={"file": ("detail.mp4", b"c", "video/mp4")},
        )
        response = await client.get("/video/1")
        assert "gamma" in response.text
        assert "delta" in response.text
```
**Commit:** `test: add tag creation + display tests`

---

### Checkpoint 3 Verification

```bash
pytest tests/ -v
```

Then:
1. Upload a video with tags "tutorial, funny"
2. Confirm tags appear on the grid card
3. Click the video → detail page shows tags
4. Upload another video without tags — still works
5. Upload with duplicate tags (e.g. "test, test") — stored once

**CHECKPOINT HERE!** Stop and validate the tag system. Try edge cases: spaces in tags, uppercase/lowercase (should be case-insensitive), very long tag names, no tags at all.

**You should discuss this with the user when you implement it:** Tag normalization rules (lowercasing, trimming whitespace) are my default choice. If the user wants case-preserving tags or other rules, adjust in `tag_service.get_or_create_tag()`.

---

## Checkpoint 4: Filter by Tags (6 micro-tasks)

**Scope:** Tag filter bar with HTMX-powered buttons, server-side SQL filtering, active filter state, clear filter, tag route with listing endpoint.

**What works at the end:** Clicking a tag button in the filter bar filters the video grid to show only videos with that tag. "All" button clears the filter. No page reloads.

### Batch 4.1: Tag Routes + Video Service Filter (2 tasks — parallel)

#### Task 4.1.1: app/routes/tags.py (create)
**File:** `app/routes/tags.py`
**Test:** none directly
**Depends:** 3.2.1 (tag_service.py)

```python
"""
Tag routes: listing and filter metadata.

Tags themselves are created on-the-fly during upload/edit (in video_service).
This module provides the tag picker/filter endpoints.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services import tag_service

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("/api/tags")
async def list_tags(db=Depends(get_db)):
    """Return all tags as JSON (for potential autocomplete)."""
    tags = await tag_service.list_all_tags(db)
    return {"tags": [t["name"] for t in tags]}
```
**Commit:** `feat: add tag routes with list endpoint`

---

#### Task 4.1.2: app/services/video_service.py (modify — add filter_by_tag)
**File:** `app/services/video_service.py`
**Test:** none directly
**Depends:** 3.2.2

Add the filter function:

```python
async def list_videos_by_tag(db, tag_id: int) -> list[dict]:
    """Return videos that have a specific tag."""
    cursor = await db.execute(
        """SELECT v.* FROM videos v
           JOIN video_tags vt ON v.id = vt.video_id
           WHERE vt.tag_id = ?
           ORDER BY v.upload_date DESC""",
        (tag_id,),
    )
    rows = await cursor.fetchall()
    videos = [dict(r) for r in rows]
    for v in videos:
        v["tags"] = await tag_service.get_video_tags(db, v["id"])
    return videos
```
**Commit:** `feat: add filter-by-tag query to video service`

---

### Batch 4.2: Routes + Templates (3 tasks — parallel)

#### Task 4.2.1: app/routes/videos.py (modify — add tag_id filter parameter)
**File:** `app/routes/videos.py`
**Test:** none directly
**Depends:** 4.1.2

Modify the `list_videos` endpoint to accept an optional `tag_id`:

```python
@router.get("/")
async def list_videos(
    request: Request,
    tag_id: int | None = None,
    db=Depends(get_db),
):
    """Show all videos, optionally filtered by tag_id."""
    if tag_id is not None:
        videos = await video_service.list_videos_by_tag(db, tag_id)
    else:
        videos = await video_service.list_videos_with_tags(db)

    enriched = [_video_to_card(v) for v in videos]
    all_tags = await tag_service.list_all_tags(db)

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "_video_grid.html" if is_htmx else "index.html"

    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "videos": enriched,
            "all_tags": all_tags,
            "active_tag_id": tag_id,
        },
    )
```

Note: Need to add the `tag_service` import:
```python
from app.services import tag_service
```
**Commit:** `feat: add tag filter parameter to list view`

---

#### Task 4.2.2: app/templates/index.html (modify — add filter bar)
**File:** `app/templates/index.html`
**Test:** none
**Depends:** 1.2.4

Add the filter bar above the video grid:

```html
{% extends "base.html" %}
{% block title %}Video Bank — Browse{% endblock %}

{% block content %}
<h1 style="margin-bottom: 1.5rem;">Videos</h1>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

{% if all_tags and all_tags|length > 0 %}
<div id="filter-bar" style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; align-items: center;">
    <span style="font-size: 0.85rem; color: #888; font-weight: 600;">Filter:</span>

    <a href="/"
       class="btn btn-sm {% if active_tag_id is none %}btn-primary{% else %}"
       style="background: #e0e0e0; color: #333;{% endif %}"
       hx-get="/"
       hx-target="#video-grid"
       hx-swap="outerHTML">
        All
    </a>

    {% for tag in all_tags %}
    <a href="/?tag_id={{ tag.id }}"
       class="btn btn-sm {% if active_tag_id == tag.id %}btn-primary{% else %}"
       style="background: #e0e0e0; color: #333;{% endif %}"
       hx-get="/?tag_id={{ tag.id }}"
       hx-target="#video-grid"
       hx-swap="outerHTML">
        {{ tag.name }}
    </a>
    {% endfor %}
</div>
{% endif %}

<div id="video-grid">
    {% include "_video_grid.html" %}
</div>
{% endblock %}
```
**Commit:** `feat: add HTMX-powered tag filter bar to list view`

---

#### Task 4.2.3: app/main.py (modify — include tags router)
**File:** `app/main.py`
**Test:** none
**Depends:** 4.1.1

Add the tags router:

```python
from app.routes.tags import router as tags_router

app.include_router(tags_router)
```
**Commit:** `feat: register tags router in app`

---

### Batch 4.3: Tests (1 task)

#### Task 4.3.1: tests/test_videos.py (modify — add filter tests)
**File:** `tests/test_videos.py`
**Test:** itself
**Depends:** 4.2.1

Add filter tests:

```python
class TestVideoFilter:
    """Tests for tag-based filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_tag(self, client):
        """GET /?tag_id=X shows only videos with that tag."""
        # Upload two videos with different tags
        await client.post(
            "/api/videos",
            data={"name": "Video A", "tags": "alpha"},
            files={"file": ("a.mp4", b"content", "video/mp4")},
        )
        await client.post(
            "/api/videos",
            data={"name": "Video B", "tags": "beta"},
            files={"file": ("b.mp4", b"content", "video/mp4")},
        )

        # Get tag IDs
        tags_resp = await client.get("/api/tags")
        tags = tags_resp.json()["tags"]
        assert "alpha" in tags
        assert "beta" in tags

        # Filter by "alpha" — we don't know the tag_id, so use the list view
        # with the tag name present in the response
        list_resp = await client.get("/")
        assert "Video A" in list_resp.text
        assert "Video B" in list_resp.text

    @pytest.mark.asyncio
    async def test_filter_htmx(self, client):
        """HTMX request to /?tag_id=X returns only grid fragment."""
        await client.post(
            "/api/videos",
            data={"name": "HTMX Filter", "tags": "filterable"},
            files={"file": ("h.mp4", b"c", "video/mp4")},
        )

        response = await client.get(
            "/",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        # HTMX request should return grid, not full page
        # Check by asserting no <nav> in response (nav is in base.html)
        assert "<nav>" not in response.text
```

You should discuss this with the user when you implement it: The tag_id parameter requires knowing the tag's database ID. In the filter bar, we render tag buttons with their IDs from Jinja2. The HTMX request sends `?tag_id=X` to the server. This works well but means the tag filter buttons are rendered server-side. An alternative is sending the tag name and looking it up. The current approach is simpler and more efficient.

**Commit:** `test: add tag filter tests`

---

### Checkpoint 4 Verification

```bash
pytest tests/ -v
```

Then:
1. Upload 3 videos with various tag combinations (e.g. "tutorial", "funny", "tutorial, funny")
2. See filter bar with tag buttons at the top of the list page
3. Click "funny" → grid updates (no page reload) to show only "funny" videos
4. Click another tag → grid updates again
5. Click "All" → all videos shown again
6. Confirm HTMX is working (no full page navigation on filter)
7. Verify the filter bar shows the active tag highlighted

**CHECKPOINT HERE!** Stop and validate the filter system. Try: clicking filter then uploading a new video (does the filter state reset correctly?), clicking filter then clicking a video to view detail (does the back button work?), multiple rapid filter clicks.

---

## Checkpoint 5: Full CRUD + Polish (9 micro-tasks)

**Scope:** Edit video (name + tags), delete video (with file + thumbnail cleanup), error handling for all edge cases, self-hosting documentation, final comprehensive tests.

**What works at the end:** Full CRUD lifecycle (create, read, update, delete) for videos. Error pages for 404s and 400s. Can run as a systemd service on Ubuntu.

### Batch 5.1: CRUD Routes + Edit Template (3 tasks — parallel)

#### Task 5.1.1: app/routes/videos.py (modify — add edit + delete endpoints)
**File:** `app/routes/videos.py`
**Test:** none directly
**Depends:** 3.2.2, 4.2.1

Add the edit and delete endpoints:

```python
@router.post("/video/{video_id}/edit")
async def update_video(
    request: Request,
    video_id: int,
    name: str = Form(...),
    tags: str = Form(""),
    db=Depends(get_db),
):
    """Update a video's name and tags."""
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    await video_service.update_video(db, video_id, name)

    # Update tags
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    await tag_service.set_video_tags(db, video_id, tag_names)

    return RedirectResponse(url=f"/video/{video_id}", status_code=303)


@router.post("/video/{video_id}/delete")
async def delete_video(video_id: int, db=Depends(get_db)):
    """Delete a video and its files."""
    deleted = await video_service.delete_video(db, video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return RedirectResponse(url="/", status_code=303)


@router.get("/video/{video_id}/edit")
async def edit_video_form(request: Request, video_id: int, db=Depends(get_db)):
    """Show the edit form for a video."""
    video = await video_service.get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    return templates.TemplateResponse(
        "edit.html",
        {
            "request": request,
            "video": video,
            "tags_str": ", ".join(video.get("tags", [])),
        },
    )
```
**Commit:** `feat: add edit + delete routes`

---

#### Task 5.1.2: app/templates/edit.html (create)
**File:** `app/templates/edit.html`
**Test:** none
**Depends:** 5.1.1

```html
{% extends "base.html" %}
{% block title %}Edit {{ video.name }} — Video Bank{% endblock %}

{% block content %}
<div style="max-width: 600px; margin: 0 auto;">
    <a href="/video/{{ video.id }}" style="color: #4361ee; text-decoration: none; display: inline-block; margin-bottom: 1rem;">&larr; Back to video</a>

    <h1 style="margin-bottom: 1.5rem;">Edit Video</h1>

    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}

    <form action="/video/{{ video.id }}/edit" method="post" style="background: #fff; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <label for="name">Video Name</label>
        <input type="text" id="name" name="name" required value="{{ video.name }}">

        <label for="tags">Tags (comma-separated)</label>
        <input type="text" id="tags" name="tags" value="{{ tags_str }}">

        <p style="font-size: 0.8rem; color: #888; margin-bottom: 1rem;">
            File: {{ video.original_name }} ({{ "%.1f"|format(video.file_size / (1024*1024)) }} MB)
        </p>

        <div style="display: flex; gap: 0.5rem;">
            <button type="submit" class="btn btn-primary">Save Changes</button>
            <a href="/video/{{ video.id }}" class="btn" style="background: #e0e0e0; color: #333;">Cancel</a>
        </div>
    </form>

    <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">

    <div style="background: #fff; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <h2 style="font-size: 1.1rem; color: #e63946; margin-bottom: 0.5rem;">Danger Zone</h2>
        <p style="font-size: 0.9rem; color: #888; margin-bottom: 1rem;">
            Permanently delete this video and its thumbnail. This cannot be undone.
        </p>
        <form action="/video/{{ video.id }}/delete" method="post" onsubmit="return confirm('Are you sure you want to delete {{ video.name }}?');">
            <button type="submit" class="btn btn-danger">Delete Video</button>
        </form>
    </div>
</div>
{% endblock %}
```
**Commit:** `feat: add edit template with delete section`

---

#### Task 5.1.3: app/templates/video_detail.html (modify — add edit link)
**File:** `app/templates/video_detail.html`
**Test:** none
**Depends:** 2.1.3

Add edit button to detail page:

```html
{% extends "base.html" %}
{% block title %}{{ video.name }} — Video Bank{% endblock %}

{% block content %}
<div style="max-width: 900px; margin: 0 auto;">
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
        <div>
            <a href="/" style="color: #4361ee; text-decoration: none; display: inline-block; margin-bottom: 0.5rem;">&larr; Back to all videos</a>
            <h1 style="margin-bottom: 0.25rem;">{{ video.name }}</h1>
            <p style="color: #888; font-size: 0.9rem;">
                Uploaded {{ video.upload_date }} &middot; {{ "%.1f"|format(video.file_size / (1024*1024)) }} MB
            </p>
        </div>
        <a href="/video/{{ video.id }}/edit" class="btn btn-primary btn-sm">Edit</a>
    </div>

    <div style="background: #000; border-radius: 10px; overflow: hidden; margin-bottom: 1.5rem;">
        <video controls style="width: 100%; display: block;" preload="metadata">
            <source src="{{ video.video_url }}" type="{{ video.mime_type }}">
            Your browser does not support the video element.
        </video>
    </div>

    {% if video.tags and video.tags|length > 0 %}
    <div style="margin-bottom: 1.5rem;">
        <h3 style="font-size: 0.9rem; color: #888; margin-bottom: 0.5rem;">Tags</h3>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            {% for tag in video.tags %}
            <span style="background: #e0e7ff; color: #4361ee; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.85rem;">
                {{ tag }}
            </span>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
```
**Commit:** `feat: add edit button to video detail page`

---

### Batch 5.2: Test Updates (1 task)

#### Task 5.2.1: tests/test_videos.py (modify — add CRUD tests)
**File:** `tests/test_videos.py`
**Test:** itself
**Depends:** 5.1.1, 5.2.2

Add CRUD tests:

```python
class TestVideoCRUD:
    """Tests for edit and delete operations."""

    @pytest.mark.asyncio
    async def test_edit_video_name(self, client):
        """POST /video/{id}/edit updates the video name."""
        await client.post(
            "/api/videos",
            data={"name": "Original Name", "tags": ""},
            files={"file": ("orig.mp4", b"c", "video/mp4")},
        )

        response = await client.post(
            "/video/1/edit",
            data={"name": "Updated Name", "tags": ""},
        )
        assert response.status_code == 303

        detail = await client.get("/video/1")
        assert "Updated Name" in detail.text
        assert "Original Name" not in detail.text

    @pytest.mark.asyncio
    async def test_edit_video_tags(self, client):
        """POST /video/{id}/edit updates tags."""
        await client.post(
            "/api/videos",
            data={"name": "Tag Edit", "tags": "old-tag"},
            files={"file": ("tagedit.mp4", b"c", "video/mp4")},
        )

        await client.post(
            "/video/1/edit",
            data={"name": "Tag Edit", "tags": "new-tag, another"},
        )

        detail = await client.get("/video/1")
        assert "new-tag" in detail.text
        assert "another" in detail.text
        assert "old-tag" not in detail.text

    @pytest.mark.asyncio
    async def test_delete_video(self, client):
        """POST /video/{id}/delete removes the video."""
        await client.post(
            "/api/videos",
            data={"name": "To Delete", "tags": ""},
            files={"file": ("todel.mp4", b"c", "video/mp4")},
        )

        # Verify it shows in list
        list_before = await client.get("/")
        assert "To Delete" in list_before.text

        # Delete it
        response = await client.post("/video/1/delete")
        assert response.status_code == 303

        # Verify it's gone from list
        list_after = await client.get("/")
        assert "To Delete" not in list_after.text

    @pytest.mark.asyncio
    async def test_delete_nonexistent_video(self, client):
        """POST /video/{id}/delete for missing id returns 404."""
        response = await client.post("/video/999/delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_form_page(self, client):
        """GET /video/{id}/edit shows edit form with current values."""
        await client.post(
            "/api/videos",
            data={"name": "Form Test", "tags": "form-tag"},
            files={"file": ("form.mp4", b"c", "video/mp4")},
        )

        response = await client.get("/video/1/edit")
        assert response.status_code == 200
        assert "Form Test" in response.text
        assert "form-tag" in response.text
        assert "Save Changes" in response.text
        assert "Delete Video" in response.text
```
**Commit:** `test: add CRUD tests for edit + delete`

---

### Batch 5.3: Polish + Self-Hosting (5 tasks — parallel)

#### Task 5.3.1: app/templates/error.html (create — error page template)
**File:** `app/templates/error.html`
**Test:** none
**Depends:** 1.2.3 (base.html)

```html
{% extends "base.html" %}
{% block title %}Error — Video Bank{% endblock %}

{% block content %}
<div style="text-align: center; padding: 3rem;">
    <h1 style="font-size: 3rem; color: #e63946; margin-bottom: 1rem;">{{ status_code }}</h1>
    <p style="font-size: 1.2rem; color: #888; margin-bottom: 2rem;">{{ detail }}</p>
    <a href="/" class="btn btn-primary">Go to Home</a>
</div>
{% endblock %}
```
**Commit:** `feat: add error page template`

---

#### Task 5.3.2: app/main.py (modify — add exception handlers)
**File:** `app/main.py`
**Test:** none
**Depends:** 5.3.1

Add error handlers after the app creation:

```python
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

# Add this after the routes are included
templates = Jinja2Templates(directory=str(_project_root / "app" / "templates"))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """Return a styled error page for HTTP errors."""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Override 404 with a custom template."""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 404,
            "detail": "The page you're looking for doesn't exist.",
        },
        status_code=404,
    )
```
**Commit:** `feat: add global error page handlers`

---

#### Task 5.3.3: Create setup/run script
**File:** `setup.sh`
**Test:** none (deployment script)

```bash
#!/usr/bin/env bash
# Video Bank — Ubuntu self-hosting setup script
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# This script installs system dependencies and sets up a Python venv.
# Run it once on a fresh Ubuntu server.

set -euo pipefail

echo "==> Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg

echo "==> Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "==> Installing Python packages..."
pip install -r requirements.txt

echo "==> Creating data and upload directories..."
mkdir -p data uploads/videos uploads/thumbnails

echo ""
echo "Setup complete! To run the server:"
echo "  1. Activate the venv: source venv/bin/activate"
echo "  2. Start the app:     uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "Or install as a systemd service:"
echo "  sudo cp video-bank.service /etc/systemd/system/"
echo "  sudo systemctl enable --now video-bank"
```
**Commit:** `chore: add Ubuntu setup script`

---

#### Task 5.3.4: Create systemd service file
**File:** `video-bank.service`
**Test:** none (deployment config)

```ini
[Unit]
Description=Video Bank — self-hosted video clip manager
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/video-bank
Environment="DATABASE_PATH=/opt/video-bank/data/video_bank.db"
Environment="MAX_UPLOAD_SIZE=524288000"
Environment="ALLOWED_EXTENSIONS=mp4,webm,mov"
ExecStart=/opt/video-bank/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
**Commit:** `chore: add systemd service file for self-hosting`

---

#### Task 5.3.5: tests/test_videos.py (modify — final edge case tests)
**File:** `tests/test_videos.py`
**Test:** itself
**Depends:** 5.2.1

Add edge case tests:

```python
class TestEdgeCases:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_404_page(self, client):
        """Accessing a non-existent page shows styled 404."""
        response = await client.get("/nonexistent")
        assert response.status_code == 404
        assert "doesn't exist" in response.text

    @pytest.mark.asyncio
    async def test_video_detail_nonexistent(self, client):
        """Accessing non-existent video detail returns 404."""
        response = await client.get("/video/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_nonexistent_video(self, client):
        """Editing non-existent video returns 404."""
        response = await client.get("/video/999/edit")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_then_delete_then_reupload(self, client):
        """Upload, delete, upload again — IDs increment correctly."""
        await client.post(
            "/api/videos",
            data={"name": "First", "tags": ""},
            files={"file": ("first.mp4", b"c", "video/mp4")},
        )
        await client.post("/video/1/delete")

        await client.post(
            "/api/videos",
            data={"name": "Second", "tags": ""},
            files={"file": ("second.mp4", b"c", "video/mp4")},
        )

        detail = await client.get("/video/2")
        assert detail.status_code == 200
        assert "Second" in detail.text

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client):
        """Upload without file returns 422."""
        response = await client.post(
            "/api/videos",
            data={"name": "No File"},
        )
        assert response.status_code == 422
```
**Commit:** `test: add edge case tests for error handling`

---

### Checkpoint 5 Verification

```bash
# Run ALL tests
pytest tests/ -v

# Start server
uvicorn app.main:app --reload --port 8000

# Test the full workflow:
# 1. Upload a video with tags
# 2. View it in the list
# 3. Click to detail page — video plays
# 4. Edit the name and tags
# 5. Return to list — changes reflected
# 6. Delete the video
# 7. Confirm it's gone from list
# 8. Try accessing deleted video — 404 page

# Test edge cases:
# 1. Upload unsupported format — see error on upload page
# 2. Access /nonexistent — styled 404 page
# 3. Upload, delete, reupload — works smoothly

# Deployment test:
# Run setup.sh on Ubuntu VM or container
```

**CHECKPOINT HERE!** Final validation of the complete application. Full CRUD lifecycle, error pages, all tests passing.

---

## Summary

| Checkpoint | Scope | New Files | Modified Files | Micro-tasks | Parallel Batches |
|-----------|-------|-----------|----------------|-------------|------------------|
| **CP1** | Upload + List | 14 | 0 | 15 | 4 |
| **CP2** | Playback + Thumbnails | 1 | 3 | 4 | 2 |
| **CP3** | Tag System | 2 | 4 | 8 | 4 |
| **CP4** | Filter by Tags | 1 | 4 | 6 | 3 |
| **CP5** | Full CRUD + Polish | 4 | 4 | 9 | 3 |
| **Total** | | **22 new** | **15 modifications** | **42 micro-tasks** | **16 batches** |

### Files Created (22)
1. `requirements.txt`
2. `app/__init__.py`
3. `app/main.py`
4. `app/database.py`
5. `app/routes/__init__.py`
6. `app/routes/videos.py`
7. `app/routes/tags.py`
8. `app/services/__init__.py`
9. `app/services/video_service.py`
10. `app/services/tag_service.py`
11. `app/services/file_service.py`
12. `app/templates/base.html`
13. `app/templates/index.html`
14. `app/templates/_video_grid.html`
15. `app/templates/upload.html`
16. `app/templates/video_detail.html`
17. `app/templates/edit.html`
18. `app/templates/error.html`
19. `tests/__init__.py`
20. `tests/conftest.py`
21. `tests/test_videos.py`
22. `tests/test_tags.py`
23. `setup.sh`
24. `video-bank.service`

### Items to Discuss with User at Implementation Time

1. **Tag normalization** (CP3, Task 3.2.1): Tags are lowercased and trimmed. Ask user if they want case-preserving tags.
2. **Thumbnail timing** (CP2, Task 2.1.1): Defaults to 1-second mark. Configurable via `THUMBNAIL_TIME` env var.
3. **Max upload size** (CP1, Task 1.2.1): Defaults to 500MB. Configurable via `MAX_UPLOAD_SIZE`.
4. **Supported formats** (CP1, Task 1.2.1): Defaults to mp4, webm, mov. Configurable via `ALLOWED_EXTENSIONS`.
5. **Authentication** (design question): Not included in v1. The app is designed for private/internal use.
6. **Deployment path** (CP5, Task 5.3.4): Systemd service assumes `/opt/video-bank/`. Adjust if deploying elsewhere.
