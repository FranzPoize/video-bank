---
date: 2026-05-14
topic: "Video Clip Bank Web App"
status: validated
---

## Problem Statement

Build a self-hosted web application where users can upload video clips, browse them via thumbnails, play them in-browser, tag them with arbitrary labels, and filter the collection by tags. The app must be simple, testable, and easy to deploy on Ubuntu with minimal dependencies.

## Constraints

- **Must be easy to self-host on Ubuntu** — no heavy infrastructure (no Docker requirement, no Postgres, no build toolchain)
- **Code must be simple** — no inversion of control, no complex abstractions
- **Code must be testable** — unit tests required, database must be swappable for in-memory in tests
- **Incremental delivery** — working checkpoints, each independently testable by the user
- **Avoid SPAs** — no React/Vue build step, server-rendered HTML only

## Approach

**Chosen stack: Python + FastAPI + Jinja2 templates + HTMX + SQLite**

Why this stack:

- **FastAPI** gives us async request handling (good for file uploads), automatic request validation via Pydantic, and built-in OpenAPI docs — all without adding IoC or heavy framework patterns
- **Jinja2 + HTMX** means no frontend build step. HTMX handles interactivity (tag filtering, delete confirmation) via HTML attributes that call server endpoints. No JavaScript framework, no npm, no webpack
- **SQLite via aiosqlite** — zero-config database, trivial to swap to `:memory:` for tests. No ORM (avoids SQLAlchemy's IoC patterns). Raw SQL for queries
- **ffmpeg via subprocess** — thumbnail generation. ffmpeg is `apt install` on Ubuntu, no Python bindings needed

Alternatives considered and rejected:
- **Flask:** Synchronous, no built-in validation, would need more boilerplate for the same result
- **Django:** Too heavy — ORM, admin, middleware stack are unnecessary for a 3-page CRUD app
- **Node.js/Express:** More complex self-hosting (nvm/npm), no significant advantage for this use case
- **React/Vue:** Build step, toolchain, JS fatigue — zero benefit for a server-rendered app with minimal interactivity

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Browser                     │
│  Jinja2 HTML + HTMX (no JS build step)      │
└──────────────┬──────────────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────────────┐
│              FastAPI Server                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Upload   │  │ Video    │  │ Tag       │  │
│  │ Routes   │  │ Routes   │  │ Routes    │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │              │         │
│  ┌────▼──────────────▼──────────────▼─────┐  │
│  │         Service Layer                  │  │
│  │  (video_service, tag_service)          │  │
│  └────┬─────────────────────────────┬─────┘  │
│       │                             │         │
│  ┌────▼─────┐              ┌───────▼──────┐  │
│  │ SQLite   │              │  Filesystem  │  │
│  │ (aiosqlite)             │  uploads/    │  │
│  └──────────┘              └──────────────┘  │
└──────────────────────────────────────────────┘
```

**Key architectural decisions:**
- Routes are thin — they validate input, call a service, return a response (JSON or HTML template)
- Service layer contains business logic (tag parsing, file handling, thumbnail generation)
- Database layer is raw SQL executed against an aiosqlite connection — no ORM, no query builder
- Templates are Jinja2 — rendered server-side, HTMX handles partial updates for filtering

## Components

### 1. Routes (controllers)
- `videos.py` — Upload, list, get, edit, delete endpoints
- `tags.py` — Tag listing (tags are created on-the-fly during upload/edit)

Each route function:
1. Takes request data (validated by Pydantic models)
2. Calls service function
3. Returns a template (for page loads) or an HTMX fragment (for partial updates)

### 2. Services
- `video_service.py` — create_video, get_video, list_videos, update_video, delete_video, filter_by_tags
- `tag_service.py` — get_or_create_tag, list_all_tags, get_video_tags
- `file_service.py` — save_upload, delete_file, generate_thumbnail (ffmpeg subprocess)

### 3. Database
- `database.py` — Connection management, initialization, migration helper
- SQL schema (applied on startup):
  - `videos` table: id (INTEGER PK), name (TEXT), filename (TEXT), original_name (TEXT), mime_type (TEXT), file_size (INTEGER), upload_date (TIMESTAMP)
  - `tags` table: id (INTEGER PK), name (TEXT UNIQUE)
  - `video_tags` table: video_id (FK), tag_id (FK), UNIQUE(video_id, tag_id)

### 4. Templates
- `base.html` — HTML shell with HTMX loaded, CSS, nav
- `index.html` — Video grid with thumbnails + tag filter bar (HTMX-powered)
- `upload.html` — Upload form (name, file, tags)
- `edit.html` — Edit form for existing video
- `video_detail.html` — Video player + metadata

### 5. Static files
- Served by FastAPI's `StaticFiles` mount
- `uploads/videos/` — raw uploaded video files
- `uploads/thumbnails/` — generated .jpg thumbnails

## Data Flow

### Upload Flow
```
User submits form (name + file + tags)
  → FastAPI validates with Pydantic (UploadVideo schema)
  → video_service.create_video():
      1. Save file to uploads/videos/{uuid}.{ext}
      2. Run ffmpeg to extract frame → uploads/thumbnails/{uuid}.jpg
      3. INSERT into videos table
      4. Parse tags (comma-separated), get_or_create each, INSERT into video_tags
  → Return redirect to list page
```

### List + Filter Flow
```
Page load:
  → GET / → video_service.list_videos()
  → Returns all videos with their tags
  → Renders index.html

Filter by tag:
  → Click tag button → HTMX sends GET /?tag_id=X
  → video_service.list_videos(tag_id=X)
    → SELECT v.* FROM videos v
      JOIN video_tags vt ON v.id = vt.video_id
      WHERE vt.tag_id = ?
  → Renders just the video grid fragment
  → HTMX swaps the grid in-place (no full page reload)
```

### Playback Flow
```
Click thumbnail
  → GET /video/{id}
  → Renders video_detail.html with <video> element
  → <video src="/api/video/{id}/file"> streams the file
  → FastAPI streams file using FileResponse (range requests supported for seeking)
```

## Error Handling

- **File too large:** FastAPI's `max_file_size` config (env var `MAX_UPLOAD_SIZE`, default 500MB)
- **Unsupported format:** Validate against allowlist on upload (env var `ALLOWED_EXTENSIONS`, default mp4,webm,mov)
- **Missing ffmpeg:** Check on startup, serve degraded (no thumbnails, show placeholder)
- **File not found on disk:** Return 404 with error page, database row cleaned up on next error check
- **Database errors:** Wrapped in service layer, raise HTTPException with appropriate status
- **HTMX errors:** Return 204 + `HX-Trigger` for toast notifications on the frontend

## Testing Strategy

- **pytest** as the test runner
- **httpx.AsyncClient** for FastAPI endpoint testing (async)
- In-memory SQLite for each test (fixture creates fresh DB + applies schema)
- **Test categories:**
  - Unit tests for service functions (video_service, tag_service)
  - Integration tests for routes (upload, list, filter, edit, delete)
  - File handling tests (upload file, verify it's saved, verify thumbnail exists)
  - Filter tests (create videos with tags, verify filter returns correct subset)
  - Edge cases: duplicate tags, empty tag string, very large filename, unsupported format

**What we don't test (yet):**
- ffmpeg behavior itself (we test that it's called, not that it produces correct output)
- Browser-level behavior (no Selenium/Playwright in initial pass)

## Open Questions

- **Max upload size:** Defaulting to 500MB, configurable via `MAX_UPLOAD_SIZE` env var. Discuss if needed.
- **Supported formats:** Defaulting to mp4, webm, mov. Configurable via `ALLOWED_EXTENSIONS`. Discuss if needed.
- **Thumbnail timing:** Grabbing frame at 1-second mark. Can be adjusted to a percentage or configurable time offset.
- **Tag input UX:** Comma-separated text input in v1. Could be upgraded to autocomplete/multi-select later.
- **Authentication:** Not included in v1. The app is designed for private/internal use. Add if needed.

## Incremental Plan (5 Checkpoints)

### Checkpoint 1: Upload + List
- FastAPI project skeleton with proper structure
- SQLite schema + DB init on startup
- Upload endpoint (POST /api/videos) with file save
- List endpoint (GET /) with Jinja2 template
- Basic HTML page showing uploaded videos

### Checkpoint 2: Playback + Thumbnails
- Video streaming endpoint with range support
- ffmpeg thumbnail generation on upload
- Thumbnail display in list view
- Video detail page with <video> player

### Checkpoint 3: Tag System
- Tags table + video_tags join table
- On-the-fly tag creation during upload
- Display tags on video cards
- Tag editing (add/remove on existing videos)

### Checkpoint 4: Filter by Tags
- HTMX-powered tag filter buttons
- Server-side SQL filtering
- Active filter state + clear filter
- No page reload filtering

### Checkpoint 5: Full CRUD + Polish
- Edit video (name, tags)
- Delete video (file + DB row + thumbnail)
- Error handling for all edge cases
- Ubuntu self-hosting docs (systemd service, setup script)
- Unit tests for all endpoints
