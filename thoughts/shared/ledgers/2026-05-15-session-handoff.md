# Session: 2026-05-15 Session Handoff
Updated: 2026-05-15T00:00:00Z

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

## Progress
### Done
- [x] Checkpoints 1-5: Upload, list, playback, thumbnails, tags, tag filtering (HTMX), full CRUD (edit name/tags, delete with cascade)
- [x] Clip Creator CP1: Async upload with XHR progress, sessionStorage persistence, bottom-left popup
- [x] Clip Creator CP2: Dual-handle range seeker + click-to-seek (clipper.js), ffmpeg `-c copy` clipping (clip_service.py), migration v4 (source_video_id, clip_start, clip_end), clips inherit source tags
- [x] Responsive video player: CSS classes replacing inline styles, media queries (768px, 480px), desktop (>=1200px) uses `width: min(90vw, 1400px)` with `left:50%; transform:translateX(-50%)` centering
- [x] Bug fixes: HTMX filter target destruction (moved #main-content into _content.html), duplicate column migration error (try/except), desktop centering (switched from negative margins to position/transform trick)
- [x] **App Logging (NEW)**: File-based logging with rotation, systemd integration, logrotate support
  - `app/main.py`: `logging.basicConfig()` at startup with `force=True` (guarded in tests)
  - Service layer logging: `file_service.py`, `video_service.py`, `clip_service.py` all have log calls
  - `video-bank.service`: `ExecStartPre` creates log dir, `LOG_DIR` env var
  - `logrotate.conf`: reference config with `copytruncate` (30-day retention)
  - `tests/test_logging.py`: 11 caplog tests verifying log output
- [x] **All 63 tests passing** (52 existing + 11 new logging tests)

### In Progress
- [ ] No active work

### Blocked
- None

## Recent Commits (ahead of origin/master)
1. `84c6111` — App logging: file-based logging with systemd + logrotate support
2. `d1a8e98` — Design doc: App logging — file-based logging with logrotate

## Key Decisions (New)
- **Three-layer logging stack**: (1) Python `logging.basicConfig()` writes to file; (2) systemd `ExecStartPre` creates log dir; (3) logrotate with `copytruncate` handles rotation
- **`force=True` + test guard**: `logging.basicConfig(force=True)` overrides uvicorn's logger setup; guarded with `if "PYTEST_CURRENT_TEST" not in os.environ` so pytest's `caplog` works
- **`copytruncate` for logrotate**: App keeps writing to same file handle; logrotate copies then truncates — no `SIGHUP` handling needed
- **Logger per module**: Each service file gets `logger = logging.getLogger(__name__)` — root logger config propagates to all children
- **Service user is `ubuntu`**: Design mentioned `www-data`, but existing service uses `User=ubuntu` — kept consistent to avoid surprises

## Next Feature Ready: Available Disk Space
**Design:** `thoughts/shared/designs/2026-05-15-available-space-design.md` (validated)
**Plan:** `thoughts/shared/plans/2026-05-15-available-space-plan.md`

This feature adds:
- Nav bar space indicator (HTMX fragment, color-coded: green/yellow/red based on % free)
- Upload guard rejecting uploads that would exceed 95% disk capacity
- 7 new tests

**Files to change:**
- `app/services/file_service.py` — Add `get_available_space()` + extend `validate_file()`
- `app/templates/_space_fragment.html` — **NEW** space indicator partial
- `app/routes/videos.py` — Add `GET /api/space` endpoint
- `app/templates/base.html` — Add CSS rules + HTMX span in nav
- `tests/test_videos.py` — Add `TestDiskSpace` class with 7 tests

## Next Steps (Original List)
1. Test responsive video player sizing on desktop, adjust if needed
2. Migrate `@app.on_event("startup")` to FastAPI lifespan handlers (deprecation warning)
3. Client-side form validation in upload.js (file size, format)
4. Pagination / infinite scroll for video list
5. Push to GitHub remote
6. End-to-end user documentation (self-hosting, clip feature)

## Critical Context
- **Project root**: `/home/franz/project/video-bank`
- **Venv**: `.venv/`
- **DB file**: `data/video_bank.db` (`:memory:` in tests via `DATABASE_PATH` env var)
- **App port**: 8000
- **Tests**: `pytest -q` (63 passed)
- **Last commit**: `84c6111` — "App logging: file-based logging with systemd + logrotate support"
- **Uncommitted**:
  - `available_space.md` deleted + `old_plan/available_space.md` (appears to be a rename in progress)
  - `future_plans.md`, `i18n.md` (user-created notes)
  - `.gitignore` modified (added `logs/`)
- **Migration versions**: v1 (videos), v2 (reserved), v3 (tags + video_tags), v4 (source_video_id, clip_start, clip_end)
- **HTMX filter**: swaps `#main-content` with `outerHTML`
- **Static files**: mounted at `/static/`, contains `js/upload.js` and `js/clipper.js`
- **Deployment**: `video-bank.service` assumes path `/opt/video-bank/`
- **ffmpeg clipping**: `-ss` before `-i` for fast seek, `-c copy` for stream copy (keyframe-aligned)
- **Log directory**: Defaults to `{project_root}/logs`; production sets `LOG_DIR=/opt/video-bank/logs`
- **Log format**: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`

## Design & Plan Documents
| Document | Path | Status |
|----------|------|--------|
| Logging Design | `thoughts/shared/designs/2026-05-15-logging-design.md` | validated |
| Logging Plan | `thoughts/shared/plans/2026-05-15-logging-implementation.md` | executed |
| Available Space Design | `thoughts/shared/designs/2026-05-15-available-space-design.md` | validated |
| Available Space Plan | `thoughts/shared/plans/2026-05-15-available-space-plan.md` | ready |
| Video Bank Design | `thoughts/shared/designs/2026-05-14-video-bank-design.md` | validated |
| Clip Creator Design | `thoughts/shared/designs/2026-05-14-clip-creator-design.md` | validated |

## Working Set
- Branch: `master`
- Key files:
  - `app/main.py` — app entry + logging config
  - `app/routes/videos.py` — route handlers
  - `app/services/clip_service.py` — ffmpeg clipping logic
  - `app/services/file_service.py` — file ops + disk space check
  - `app/services/video_service.py` — video CRUD logic
  - `app/database.py` — database module
  - `app/static/js/upload.js` — async upload with XHR progress
  - `app/static/js/clipper.js` — dual-handle range seeker
  - `app/templates/base.html` — layout + CSS styles
  - `app/templates/_content.html` — HTMX swap target wrapper (#main-content)
  - `tests/test_logging.py` — 11 caplog tests for logging
  - `tests/conftest.py` — test fixtures
  - `logrotate.conf` — reference logrotate config
  - `video-bank.service` — systemd service with logging setup
