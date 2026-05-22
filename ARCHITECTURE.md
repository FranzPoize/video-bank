# Video Bank — Architecture

## Overview

**Video Bank** is a self-hosted web application for uploading, tagging, browsing, and clipping video files. Built with Python/FastAPI, it uses SQLite for storage, Jinja2 for server-side HTML rendering, and HTMX for interactive UI updates — all served by a single Python process behind systemd on Ubuntu.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web framework** | FastAPI 0.110+ | ASGI app, routing, dependency injection |
| **Server** | uvicorn[standard] | ASGI server (port 4322 in production) |
| **Templates** | Jinja2 3.1+ + HTMX 2.0 | Server-rendered HTML with partial swaps |
| **Database** | SQLite via aiosqlite 0.20+ | Single-file relational DB, no ORM |
| **Video processing** | ffmpeg / ffprobe | Thumbnail generation, clip extraction |
| **Client-side** | Vanilla JS (no framework) | Upload progress, clip seeker UI |
| **i18n** | JSON translation files | English (base) + French, extensible |
| **Testing** | pytest 8+, pytest-asyncio, httpx | Async test client, in-memory DB |
| **Deployment** | systemd + logrotate | Ubuntu self-hosted service |

---

## Directory Structure

```
video-bank/
├── app/                          # Main application package
│   ├── main.py                   # ★ ASGI entry point (uvicorn app.main:app)
│   ├── database.py               # SQLite schema, migrations, connection factory
│   ├── templates.py              # Jinja2 setup + i18n loading
│   ├── routes/
│   │   ├── videos.py             # All video/clip/upload/list/edit/delete endpoints
│   │   └── tags.py               # Tag listing, settings page, tag CRUD endpoints
│   ├── services/
│   │   ├── video_service.py      # Video CRUD business logic
│   │   ├── tag_service.py        # Tag CRUD + video-tag associations
│   │   ├── file_service.py       # File I/O, thumbnails, disk space, validation
│   │   └── clip_service.py       # Clip extraction via ffmpeg
│   ├── static/js/
│   │   ├── upload.js             # Async upload with XHR progress popup
│   │   └── clipper.js            # Dual-handle clip seeker UI
│   └── templates/                # Jinja2 HTML templates (12 files)
│       ├── base.html             # Layout: nav, style, HTMX, JS, i18n script
│       ├── index.html            # Home: video grid + filter bar
│       ├── _content.html         # HTMX fragment: grid content
│       ├── _video_grid.html      # HTMX fragment: card grid
│       ├── _space_fragment.html  # HTMX fragment: disk space indicator
│       ├── _upload_popup.html    # HTMX fragment: upload modal popup
│       ├── upload.html           # Upload form page
│       ├── video_detail.html     # Single video player + metadata
│       ├── clip.html             # Clip creator interface
│       ├── edit.html             # Edit video/clip metadata
│       ├── settings.html         # Settings + tag management
│       └── error.html            # Error display page
├── tests/                        # Test suite (pytest)
│   ├── conftest.py               # Fixtures: in-memory DB, httpx test client
│   ├── test_videos.py            # Upload, stream, CRUD, disk space, edge cases
│   ├── test_tags.py              # Tag creation, display, service, management routes
│   ├── test_clips.py             # Clip creation validation & endpoints
│   └── test_logging.py           # Logging behavior tests
├── translations/
│   ├── en.json                   # English translations (base)
│   └── fr.json                   # French translations (overrides)
├── uploads/
│   ├── videos/                   # Stored video files (UUID-named, gitignored)
│   └── thumbnails/               # Generated thumbnails (gitignored)
├── data/
│   └── video_bank.db             # SQLite database (gitignored)
├── logs/
│   └── video-bank.log            # Application log (gitignored)
├── requirements.txt              # Python dependencies
├── setup.sh                      # Ubuntu bootstrap script
├── video-bank.service            # systemd unit definition
└── logrotate.conf                # Log rotation config
```

---

## Core Components

### 1. Entry Point — `app/main.py`

Creates the FastAPI app, mounts static/uploads directories, includes both routers, and registers:
- **Language middleware** — cookie > Accept-Language header > default "en"
- **Exception handlers** — custom 404/error pages with i18n
- **Startup event** — initializes DB (migration v4), configures file logging, checks ffmpeg

### 2. Routes Layer — `app/routes/`

Thin request/response handlers that validate input and delegate to services.

**`videos.py`** — `APIRouter` with all video-related endpoints:
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Home page / HTMX grid fragment |
| `/upload` | GET | Upload form |
| `/api/videos` | POST | Upload video (form + XHR dual-mode) |
| `/api/video/{id}/file` | GET | Stream video file |
| `/video/{id}` | GET | Detail page with player |
| `/video/{id}/edit` | GET/POST | Edit metadata form + update |
| `/video/{id}/delete` | POST | Delete video + files |
| `/video/{id}/clip` | GET | Clip creator page |
| `/api/video/{id}/clip` | POST | Create clip (JSON body) |
| `/api/space` | GET | Disk space fragment (HTMX) |
| `/api/lang` | POST | Switch language (cookie) |
| `/health` | GET | Health check (in main.py) |

**`tags.py`** — `APIRouter` with tag management:
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tags` | GET | List all tags as JSON |
| `/settings` | GET | Settings page with tag management |
| `/api/tags/{id}/rename` | POST | Rename a tag |
| `/api/tags/{id}/delete` | POST | Delete a tag |

### 3. Service Layer — `app/services/`

Business logic with no HTTP dependencies. Each service function takes an `aiosqlite.Connection` as its first argument for testability.

- **`video_service.py`** — CRUD for videos, tag-enriched queries, file validation delegation
- **`tag_service.py`** — Tag creation (on-the-fly), video-tag association (replace-all semantics), tag renames with uniqueness checks, cascading deletes
- **`file_service.py`** — UUID-based file storage, extension validation, disk space guards, ffmpeg thumbnail generation
- **`clip_service.py`** — ffmpeg subprocess management, time validation, clip metadata + tag copying from source

### 4. Database — `app/database.py`

Raw SQL via `aiosqlite`. No ORM.

**Schema (migration v4):**
```
videos
├── id              INTEGER PRIMARY KEY
├── name            TEXT
├── filename        TEXT (UUID-based stored name)
├── original_name   TEXT (user's filename)
├── mime_type       TEXT
├── file_size       INTEGER
├── upload_date     TIMESTAMP (default CURRENT_TIMESTAMP)
├── source_video_id INTEGER → videos(id)  -- for clips
├── clip_start      REAL                   -- for clips
└── clip_end        REAL                   -- for clips

tags
├── id    INTEGER PRIMARY KEY
└── name  TEXT UNIQUE (lowercased, auto-normalized)

video_tags (join table)
├── video_id  INTEGER → videos(id) ON DELETE CASCADE
└── tag_id    INTEGER → tags(id) ON DELETE CASCADE
  UNIQUE(video_id, tag_id)
```

**Migrations** — Incremental versioned SQL statements applied in order. Idempotent (uses `IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`). Duplicate column errors on `ALTER TABLE` are silently ignored.

**Pattern** — `get_db()` is a FastAPI dependency that yields an `aiosqlite.Connection`. Tests override it with `:memory:` via `app.dependency_overrides`.

### 5. Templates — `app/templates/`

Jinja2 with HTMX for dynamic updates:
- **Base layout** (`base.html`) — nav bar, space indicator, language dropdown, i18n JS bridge
- **Page templates** — extend base, fill `{% block content %}`
- **Fragments** (prefixed `_`) — loaded asynchronously via `hx-get`, swapped into the DOM
- **i18n** — `_("key")` function available in all templates; translations injected via context

### 6. Static JS — `app/static/js/`

Both files are IIFE-wrapped with `"use strict"`:
- **`upload.js`** — Intercepts upload form, creates XHR with progress events, manages a persistent popup via sessionStorage
- **`clipper.js`** — Dual-range-input seeker with min-duration enforcement, click-to-seek, async API submission

---

## Data Flow

### Upload Flow
```
User submits form
  → upload.js intercepts (XHR) or browser submits (form)
  → POST /api/videos
  → routes/videos.py:create_video()
    → video_service.create_video()
      → file_service.validate_file()         # ext check, size check, disk space guard
      → file_service.save_upload()            # UUID filename, write to uploads/videos/
      → file_service.generate_thumbnail()     # ffmpeg subprocess → uploads/thumbnails/
      → INSERT INTO videos
      → tag_service.set_video_tags()          # comma-separated → normalized tags
  → Returns: JSON {id, redirect} or HTTP 303
  → upload.js shows progress → redirects to /
```

### Clip Creation Flow
```
User sets start/end on seeker UI
  → clipper.js:onSubmit()
  → POST /api/video/{id}/clip  {start, end}
  → routes/videos.py:create_clip()
    → clip_service.create_clip()
      → video_service.get_video()             # fetch source
      → _get_video_duration()                 # ffprobe subprocess
      → _validate_times()                     # bounds checking
      → ffmpeg subprocess (stream copy)       # cut clip
      → file_service.generate_thumbnail()     # from clip's first frame
      → INSERT INTO videos (with source_video_id, clip_start, clip_end)
      → tag_service.set_video_tags()          # copy source tags
  → Returns: JSON {id, redirect}
  → clipper.js redirects to /video/{id}
```

### Page Load Flow
```
GET / (or HTMX hx-get="/?tag_id=X")
  → language_middleware sets request.state.i18n
  → routes/videos.py:list_videos()
    → video_service.list_videos_with_tags(db)
      → SELECT * FROM videos ORDER BY upload_date DESC
      → for each: tag_service.get_video_tags(db, id)
    → templates render: base.html + index.html (_content.html for HTMX)
  → Nav bar loads space indicator via hx-get="/api/space"
```

---

## External Integrations

| Integration | Purpose | How |
|------------|---------|-----|
| **ffmpeg** | Thumbnail generation, clip extraction | `asyncio.create_subprocess_exec()`, checked at startup |
| **ffprobe** | Video duration detection | `asyncio.create_subprocess_exec()` in clip_service |
| **Filesystem** | Video/thumbnail storage | `uploads/videos/`, `uploads/thumbnails/` (UUID-named) |
| **HTMX 2.0** | Dynamic page updates, partial HTML swaps | CDN-loaded in base.html |
| **systemd** | Production process management | `video-bank.service` unit |
| **logrotate** | Log rotation | `logrotate.conf` — daily, 30-day retention |

---

## Configuration

All configuration is via environment variables (no `.env` files):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/video_bank.db` | SQLite database file path |
| `LOG_DIR` | `logs/` | Log output directory |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_EXTENSIONS` | `mp4,webm,mov` | Comma-separated allowed upload formats |
| `MAX_UPLOAD_SIZE` | `2147483648` (2GB) | Max upload size in bytes |
| `THUMBNAIL_TIME` | `1` | Seconds into video for thumbnail frame |
| `EMAIL_DELIVERY_MODE` | `console` | Email delivery mode; deployment placeholder example: `smtp` |
| `EMAIL_ACCOUNT` | unset | SMTP account placeholder example: `your-gmail-address@example.com` |
| `EMAIL_PASSWORD` | unset | SMTP app password placeholder example: `your-gmail-app-password` |
| `PUBLIC_BASE_URL` | unset | Public URL placeholder example: `https://your-domain.example` |

Do not commit real credentials. Replace placeholder email and public URL values in the systemd unit or shell environment for the deployment host.

The `video-bank.service` systemd unit sets production defaults:
- Port: **4322**
- Working dir: `/home/ubuntu/video-bank`
- Restart: `always` with 5s delay

---

## Build & Deploy

### Development
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Testing
```bash
pytest tests/ -v
# Individual:
pytest tests/test_videos.py -v
pytest tests/test_tags.py -v -k "TestTagCreation"
```

### Production (Ubuntu)
```bash
# Automated setup
chmod +x setup.sh && ./setup.sh

# Manual as systemd service
sudo cp video-bank.service /etc/systemd/system/
sudo systemctl enable --now video-bank
```

### Key Design Decisions
- **No ORM** — Raw SQL via aiosqlite keeps dependencies minimal and queries explicit
- **No Docker** — Designed for direct Ubuntu deployment via systemd
- **No frontend framework** — Server-rendered HTML + HTMX + vanilla JS
- **UUID storage** — Uploaded files stored as `uuid4().hex` to prevent name collisions and path traversal
- **SQLite** — Single-file DB, no separate database server needed, backups are trivial
