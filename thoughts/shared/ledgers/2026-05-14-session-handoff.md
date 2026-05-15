# Session: 2026-05-14 Session Handoff
Updated: 2026-05-14T00:00:00Z

## Goal
Build and maintain a self-hosted video clip bank web app (FastAPI + Jinja2 + HTMX + SQLite + ffmpeg) with async upload, thumbnails, tagging, filtering, and clip creation with a dual-handle range seeker.

## Constraints
- Zero build step — server-rendered HTML, no SPA framework
- Minimal Python dependencies — no media processing libraries beyond ffmpeg/ffprobe
- HTMX swaps target `#main-content` with outerHTML — responses MUST include `id="main-content"` wrapper
- XHR upload detection: `request.headers.get("x-requested-with") == "XMLHttpRequest"` → JSON response, not RedirectResponse
- SQLite via aiosqlite; `:memory:` in tests via `DATABASE_PATH` env var
- Deployment at `/opt/video-bank/` (video_bank.service assumption)
- Preserve CSS convention: styles in `<style>` blocks in `base.html` (no separate CSS files)
- All 45 tests must pass before committing

## Progress
### Done
- [x] Checkpoints 1-5: Upload, list, playback, thumbnails, tags, tag filtering (HTMX), full CRUD (edit name/tags, delete with cascade)
- [x] Clip Creator CP1: Async upload with XHR progress, sessionStorage persistence, bottom-left popup
- [x] Clip Creator CP2: Dual-handle range seeker + click-to-seek (clipper.js), ffmpeg `-c copy` clipping (clip_service.py), migration v4 (source_video_id, clip_start, clip_end), clips inherit source tags
- [x] Responsive video player: CSS classes replacing inline styles, media queries (768px, 480px), desktop (>=1200px) uses `width: min(90vw, 1400px)` with `left:50%; transform:translateX(-50%)` centering
- [x] Bug fixes: HTMX filter target destruction (moved #main-content into _content.html), duplicate column migration error (try/except), desktop centering (switched from negative margins to position/transform trick)
- [x] All 45 tests pass (test_clips: 12, test_tags: 6, test_videos: 27)

### In Progress
- [ ] No active work — session handoff / context preservation

### Blocked
- None

## Key Decisions
- **HTMX over SPA**: Zero build step, server-rendered HTML, no client-side routing or state management
- **`#main-content` wrapping for HTMX swaps**: Both filter bar and grid inside one wrapper to prevent DOM target destruction on filter
- **`ffmpeg -c copy` for clipping**: Fast (stream copy, no re-encode) but keyframe-aligned (seeks to nearest keyframe)
- **XHR over Fetch for upload**: Native progress events (no polyfill needed), simple `xhr.upload.onprogress`
- **Migration error handling**: `try/except` on `ALTER TABLE` — simpler than maintaining a migration tracking table
- **Copy source tags to clips on creation**: Clips automatically inherit all tags from source video
- **`left:50% + translateX(-50%)` for centering**: Reliable centering of wide elements within parent containers (avoids negative margin calculation issues)
- **sessionStorage for upload persistence**: Survives navigation within the session, cleared on page close

## Next Steps
1. Test responsive video player sizing on desktop, adjust if needed
2. Migrate `@app.on_event("startup")` to FastAPI lifespan handlers (deprecation warning)
3. Client-side form validation in upload.js (file size, format)
4. Pagination / infinite scroll for video list
5. Push to GitHub remote
6. End-to-end user documentation (self-hosting, clip feature)
7. Push responsive branch or any other uncommitted changes

## File Operations
### Read
- `thoughts/shared/designs/2026-05-14-video-bank-design.md`
- `thoughts/shared/designs/2026-05-14-clip-creator-design.md`
- `thoughts/shared/plans/2026-05-14-video-bank-plan.md`
- `thoughts/shared/plans/2026-05-14-clip-creator-plan.md`

### Modified
- `thoughts/shared/ledgers/2026-05-14-session-handoff.md` (created)

## Critical Context
- **Project root**: `/home/franz/project/video-bank`
- **Venv**: `.venv/`
- **DB file**: `data/video_bank.db` (`:memory:` in tests via `DATABASE_PATH` env var)
- **App port**: 8000
- **Tests**: `pytest -q` (all 45 pass)
- **Last commit**: `0cd72de` — "Responsive video player: wider on desktop, centered properly"
- **Uncommitted**: `available_space.md` (modified, checked but empty diff — possibly permissions/mtime)
- **Migration versions**: v1 (videos), v2 (reserved), v3 (tags + video_tags), v4 (source_video_id, clip_start, clip_end)
- **HTMX filter**: swaps `#main-content` with `outerHTML`
- **Static files**: mounted at `/static/`, contains `js/upload.js` and `js/clipper.js`
- **Deployment**: `video_bank.service` assumes path `/opt/video-bank/`
- **ffmpeg clipping**: `-ss` before `-i` for fast seek, `-c copy` for stream copy (keyframe-aligned)
- **ffprobe**: used for duration validation (comes with ffmpeg)
- **No Python media libraries**: keeping dependencies minimal
- **sessionStorage**: upload persistence across navigation
- **CSS convention**: all styles in `base.html <style>` blocks — no separate CSS file
- **Conftest fixtures**: `/app/tests/conftest.py` — database, client, test video setup

## Working Set
- Branch: `master`
- Key files:
  - `app/routes/videos.py` — route handlers
  - `app/services/clip_service.py` — ffmpeg clipping logic
  - `app/database.py` — database module
  - `app/static/js/upload.js` — async upload with XHR progress
  - `app/static/js/clipper.js` — dual-handle range seeker
  - `app/templates/base.html` — layout + CSS styles
  - `app/templates/_content.html` — HTMX swap target wrapper (#main-content)
  - `app/tests/conftest.py` — test fixtures
  - `data/video_bank.db` — SQLite database
