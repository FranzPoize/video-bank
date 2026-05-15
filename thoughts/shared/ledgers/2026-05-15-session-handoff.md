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
- [x] **Available Disk Space Indicator**: Nav bar space indicator (HTMX fragment, color-coded green/yellow/red) + upload guard rejecting uploads exceeding 95% disk capacity
  - `app/services/file_service.py`: `get_available_space()` + extended `validate_file()` with 95% threshold check
  - `app/routes/videos.py`: `GET /api/space` endpoint
  - `app/templates/_space_fragment.html`: HTMX fragment
  - `app/templates/base.html`: CSS + HTMX span in nav
- [x] **App Logging**: File-based logging with rotation, systemd integration, logrotate support
  - `app/main.py`: `logging.basicConfig()` at startup with `force=True` (guarded in tests)
  - Service layer logging: `file_service.py`, `video_service.py`, `clip_service.py` all have log calls
  - `video-bank.service`: `ExecStartPre` creates log dir, `LOG_DIR` env var
  - `logrotate.conf`: reference config with `copytruncate` (30-day retention)
  - `tests/test_logging.py`: 11 caplog tests verifying log output
- [x] **Internationalization (i18n)**: Multi-language support with language switcher
  - `app/templates.py`: Shared Jinja2 config with JSON translation loading
  - `translations/en.json`, `translations/fr.json`: English + French translation files
  - `app/main.py`: Language detection middleware (cookie → Accept-Language → default)
  - `app/routes/videos.py`: `POST /api/lang` endpoint for switching languages (30-day cookie)
  - `app/templates/base.html`: Language dropdown in nav bar (🇬🇧 EN / 🇫🇷 FR) with HTMX switching
  - **All templates updated**: `{{ _("key") }}` translation function used for all user-facing text
  - **JavaScript i18n**: `upload.js` and `clipper.js` use `window.TRANSLATIONS` for translated strings
- [x] **All 63 tests passing**

### In Progress
- [ ] No active work

### Blocked
- None

## Recent Commits (ahead of origin/master)
1. `5b09770` — feat(i18n): add multi-language support with language switcher
2. `9f0ce85` — Plans adds future plan and i18n requirements
3. `5cbfdd3` — docs: add session handoff ledgers + gitignore for logs/
4. `84c6111` — App logging: file-based logging with systemd + logrotate support
5. `d1a8e98` — Design doc: App logging — file-based logging with logrotate

## Key Decisions

### Available Space
- **95% threshold for upload guard**: Rejects uploads that would push disk past 95% capacity
- **HTMX fragment for space indicator**: Loaded via `hx-get="/api/space"` on page load, no middleware needed
- **Color coding**: Green (>20% free), Yellow (10-20% free), Red (<10% free)
- **Fails-open**: If `shutil.disk_usage()` fails, uploads still work (no blocking)

### Logging
- **Three-layer logging stack**: (1) Python `logging.basicConfig()` writes to file; (2) systemd `ExecStartPre` creates log dir; (3) logrotate with `copytruncate` handles rotation
- **`force=True` + test guard**: `logging.basicConfig(force=True)` overrides uvicorn's logger setup; guarded with `if "PYTEST_CURRENT_TEST" not in os.environ` so pytest's `caplog` works
- **`copytruncate` for logrotate**: App keeps writing to same file handle; logrotate copies then truncates — no `SIGHUP` handling needed
- **Logger per module**: Each service file gets `logger = logging.getLogger(__name__)` — root logger config propagates to all children

### i18n
- **Zero new dependencies**: Uses stdlib `json` module, no Babel/gettext
- **JSON translation files**: Flat key-value format, human-editable, stored in `translations/` directory
- **Language detection priority**: `lang` cookie (30-day expiry) → `Accept-Language` header → default `"en"`
- **Jinja2 `_()` function**: Passed to every template response via `request.state.i18n` context
- **JavaScript i18n via `window.TRANSLATIONS`**: Exported in inline `<script>` in `base.html`, accessible to all JS files
- **Language dropdown in nav bar**: Shows current flag + code, opens on click, uses HTMX to switch language without full page form submit

## User Feature Requests (from thoughts/user/)
### Future Features (`thoughts/user/future-features.md`)
- Cut video from clip
- Add Match with statistics (Pts, 2PA/M, 3PA/M, RBD, PD, INT, BP, EFF, BPM)
- Link clips to Match
- Tag management (CRUD)
- Absolute cinema: mark stat events on the video
- Clip improvement: Set clip start/end to current time

### i18n Requirements (`thoughts/user/i18n-requirements.md`)
- ✅ **IMPLEMENTED**: Language of the page can be changed
- ✅ **IMPLEMENTED**: Small dropdown with flag and language short code

### Available Space Requirements (`thoughts/user/available-space-requirements.md`)
- ✅ **IMPLEMENTED**: Display available space on server
- ✅ **IMPLEMENTED**: Color-coded when space is low
- ✅ **IMPLEMENTED**: Forbid uploads exceeding 95% capacity

## Next Steps (From Original List)
1. Test responsive video player sizing on desktop, adjust if needed
2. Migrate `@app.on_event("startup")` to FastAPI lifespan handlers (deprecation warning in tests)
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
- **Last commit**: `5b09770` — "feat(i18n): add multi-language support with language switcher"
- **Migration versions**: v1 (videos), v2 (reserved), v3 (tags + video_tags), v4 (source_video_id, clip_start, clip_end)
- **HTMX filter**: swaps `#main-content` with `outerHTML`
- **Static files**: mounted at `/static/`, contains `js/upload.js` and `js/clipper.js`
- **Deployment**: `video-bank.service` assumes path `/opt/video-bank/`
- **ffmpeg clipping**: `-ss` before `-i` for fast seek, `-c copy` for stream copy (keyframe-aligned)
- **Log directory**: Defaults to `{project_root}/logs`; production sets `LOG_DIR=/opt/video-bank/logs`
- **Log format**: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`
- **Translation directory**: `{project_root}/translations/` with `en.json` and `fr.json`
- **Language cookie**: `lang`, 30-day expiry, path `/`, SameSite=Lax

## Design & Plan Documents
| Document | Path | Status |
|----------|------|--------|
| i18n Design | `thoughts/shared/designs/2026-05-15-i18n-design.md` | executed |
| Logging Design | `thoughts/shared/designs/2026-05-15-logging-design.md` | executed |
| Logging Plan | `thoughts/shared/plans/2026-05-15-logging-implementation.md` | executed |
| Available Space Design | `thoughts/shared/designs/2026-05-15-available-space-design.md` | executed |
| Available Space Plan | `thoughts/shared/plans/2026-05-15-available-space-plan.md` | executed |
| Video Bank Design | `thoughts/shared/designs/2026-05-14-video-bank-design.md` | validated |
| Clip Creator Design | `thoughts/shared/designs/2026-05-14-clip-creator-design.md` | validated |

## Working Set
- Branch: `master`
- Key files:
  - `app/main.py` — app entry + logging config + i18n middleware
  - `app/templates.py` — shared Jinja2 config + translation loading
  - `app/routes/videos.py` — route handlers + `/api/space` + `/api/lang`
  - `app/services/clip_service.py` — ffmpeg clipping logic
  - `app/services/file_service.py` — file ops + disk space check
  - `app/services/video_service.py` — video CRUD logic
  - `app/database.py` — database module
  - `app/static/js/upload.js` — async upload with XHR progress
  - `app/static/js/clipper.js` — dual-handle range seeker
  - `app/templates/base.html` — layout + CSS styles + language dropdown
  - `translations/en.json`, `translations/fr.json` — translation files
  - `tests/test_logging.py` — 11 caplog tests for logging
  - `tests/conftest.py` — test fixtures
  - `logrotate.conf` — reference logrotate config
  - `video-bank.service` — systemd service with logging setup
