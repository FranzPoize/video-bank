---
date: 2026-05-15
topic: "Fix All 13 Anti-Patterns Identified by mindmodel"
status: draft
---

## Problem Statement

The mindmodel generation identified 13 anti-patterns (AP-001 through AP-013) across the codebase — duplicated code, inconsistent naming, brittle tests, missing infrastructure, and technical debt. All need to be fixed.

## Approach

Group fixes into **4 execution batches** based on risk and dependency order. Each batch is independently testable.

**Principle:** Never break existing tests. Run full suite after each batch.

## Batch 1: Trivial Fixes (no behavior change)

### AP-012 — Remove unused `get_db` import in `video_service.py`

**File:** `app/services/video_service.py` line 10

The service layer receives `db` as a function argument, but line 10 imports `get_db` from `database.py` which is never used.

**Fix:** Delete `from app.database import get_db`

**Risk:** None. Dead import. Tests verify it's not needed.

---

### AP-013 — Add type hints for `db` parameter in service functions

**Files:** `app/services/video_service.py`, `app/services/tag_service.py`, `app/services/clip_service.py`, `app/services/file_service.py`

All service functions declare `db` as a positional argument with no type hint.

**Fix:** Add `import aiosqlite` to each service file and annotate `db: aiosqlite.Connection` on every service function that takes a db parameter. Skip `file_service.py` (it doesn't take a db parameter).

**Risk:** None. Type hints are compile-time only in Python.

---

### AP-002 — Duplicated `_get_i18n()` helper in videos.py and tags.py

**Files:**
- `app/routes/videos.py` lines 44-49
- `app/routes/tags.py` lines 18-23

Both files have an identical `_get_i18n(request)` function.

**Fix:** Move to `app/templates.py` as a public function, import it in both route files.

```python
# In app/templates.py, add:
def get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback."""
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
```

Then in both route files, replace the local `_get_i18n` with `from app.templates import get_i18n`.

**Risk:** None. Pure refactor, identical behavior.

---

### AP-004 — `_video_to_card()` logic duplicated in video_detail route

**File:** `app/routes/videos.py`

The `video_detail` route (line 227) calls `_video_to_card(video)`, then immediately overrides the thumbnail fields with inline code (lines 228-236) that reimplements the same logic.

**Fix:** Remove lines 228-236 from `video_detail`, add only the `video_url` field:

Before (lines 227-236):
```python
enriched = _video_to_card(video)
thumb_stem = Path(video["filename"]).stem
enriched["video_url"] = f"/api/video/{video_id}/file"
enriched["thumbnail_url"] = f"/uploads/thumbnails/{thumb_stem}.jpg"
enriched["has_thumbnail"] = (
    Path(__file__).resolve().parent.parent.parent
    / "uploads"
    / "thumbnails"
    / f"{thumb_stem}.jpg"
).exists()
```

After:
```python
enriched = _video_to_card(video)
enriched["video_url"] = f"/api/video/{video_id}/file"
```

**Risk:** Low. `_video_to_card` already computes `has_thumbnail` and `thumbnail_url` identically.

---

### AP-005 — Thumbnail path resolution repeated

**File:** `app/routes/videos.py`

The thumbnail path resolution (`Path(__file__).resolve().parent.parent.parent / "uploads" / "thumbnails"`) appears in `_video_to_card()` and in the old `video_detail` inline code.

**Fix:** Already resolved by AP-004 fix (the duplicate inline code is removed). The remaining path resolution lives only in `_video_to_card()` which is the canonical location.

Optionally: move `get_thumbnail_path(filename)` to `file_service.py` for reuse. This is nice-to-have but not required since the only consumer is `_video_to_card()`.

**Risk:** None.

---

## Batch 2: Moderate Changes (behavior-preserving)

### AP-008 — HTMX loaded from CDN with no fallback

**File:** `app/templates/base.html` line 7

Currently: `<script src="https://unpkg.com/htmx.org@2.0.4"></script>`

**Fix:** Download HTMX to `app/static/js/htmx.min.js`, update the script tag to reference local file.

```bash
# Download HTMX
curl -o app/static/js/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js
```

**Risk:** None. Same code, local reference.

---

### AP-009 — All CSS inline in base.html

**File:** `app/templates/base.html` lines 8-163

CSS is entirely in a `<style>` block. Extract to external file.

**Fix:**
1. Create `app/static/css/style.css` with all CSS from the `<style>` block
2. Replace `<style>...</style>` with `<link rel="stylesheet" href="/static/css/style.css">`
3. Keep only the `<style>` for any template-specific CSS (none currently)

**Risk:** Low. URL paths and file structure must match.

---

### AP-007 — Clip source not found returns 400 instead of 404

**File:**
- `app/routes/videos.py` line 350
- `app/services/clip_service.py` line 94

`clip_service.create_clip()` raises `ValueError` when source video is not found (line 94-95). The route catches all `ValueError` and returns 400 (line 349-350). A nonexistent source video is semantically a 404.

**Fix:** Raise `HTTPException` directly from the route when source is not found, before calling the service. The service already returns `None` from `get_video`, so the route can check this:

In `videos.py`, `create_clip` route — add explicit source-not-found check before calling the service:

```python
source = await video_service.get_video(db, video_id)
if source is None:
    raise HTTPException(status_code=404, detail="Source video not found")
```

Also remove the ValueError handling for this case from `clip_service.create_clip()`.

**Risk:** Low. Clearer error semantics. Update the test that checks for this (`test_clip_nonexistent_source` in `test_clips.py`).

---

### AP-001 — URL inconsistency: `/api/videos` (plural) vs `/api/video/{id}` (singular)

**File:** `app/routes/videos.py`

Collection routes use both `/api/videos` (upload) and `/api/video/{id}` (detail, clip, file).

**Fix:** Rename all singular `/api/video/` routes to `/api/videos/` for consistency. Add redirect routes from old singular URLs for backward compatibility.

Routes to rename:
- `GET /api/video/{video_id}/file` → `GET /api/videos/{video_id}/file`
- `GET /video/{video_id}` → `GET /videos/{video_id}`
- `GET /video/{video_id}/edit` → `GET /videos/{video_id}/edit`
- `POST /video/{video_id}/edit` → `POST /videos/{video_id}/edit`
- `POST /video/{video_id}/delete` → `POST /videos/{video_id}/delete`
- `GET /video/{video_id}/clip` → `GET /videos/{video_id}/clip`
- `POST /api/video/{video_id}/clip` → `POST /api/videos/{video_id}/clip`

**Important:** Internal links in templates and JS files must be updated:
- `_video_grid.html`: `/video/{{ video.id }}` → `/videos/{{ video.id }}`
- `video_detail.html`: `/video/{{ video.id }}/clip`, `/video/{{ video.id }}/edit`
- `edit.html`: `/video/{{ video.id }}`, `/video/{{ video.id }}/edit`
- `clip.html`: `/video/{{ video.id }}`
- `_content.html`: `/video/{id}` references in HTMX URLs
- `clipper.js`: `/api/video/` → `/api/videos/`

**Risk:** Medium. Many files change. Must update all internal references. Tests also reference these URLs.

---

## Batch 3: Larger Refactors

### AP-003 — sys.path manipulation in main.py and conftest.py

**Files:** `app/main.py` lines 18-20, `tests/conftest.py` lines 23-25

**Fix:** Create `pyproject.toml` with a minimal project configuration, install with `pip install -e .`, remove sys.path hacks.

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "video-bank"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
include = ["app*"]
```

Then:
```bash
pip install -e .
```

Remove sys.path blocks from `main.py` and `conftest.py`.

**Risk:** Medium. Requires pip install. May affect import resolution for tests.

---

### AP-006 — Hardcoded video/tag IDs in tests

**Files:** `tests/test_videos.py`, `tests/test_tags.py`, `tests/test_clips.py`

Tests assume IDs start at 1 and hardcode `video/1`, `video/2`, `tag/1`, etc.

**Fix:** Create a helper that extracts IDs from response data. For each test that uses hardcoded IDs, capture the ID from the upload/post response and use it.

**Risk:** Low-medium. Many small changes across all test files. Easy to miss one.

---

### AP-011 — Mock complexity in clip tests

**Files:** `tests/test_clips.py` lines 152-200, 222-263, 281-320

Three tests use deeply nested context managers (5+ levels), manual `Path` mock objects with inline class definitions, and complex `side_effects`.

**Fix:** Extract a `mock_ffmpeg()` helper context manager to `conftest.py` that sets up all the standard mocks. Each test then calls it in a single `with` block.

```python
@contextmanager
def mock_ffmpeg(db, source_filename="src.mp4", duration=60.0, returncode=0):
    """Context manager that mocks ffmpeg/ffprobe for clip tests."""
    # Set up all the standard mocks...
    yield
```

**Risk:** Low. Extracts pattern, doesn't change test logic.

---

### AP-010 — No CI pipeline

**New file:** `.github/workflows/test.yml`

**Fix:** Add a basic GitHub Actions workflow that runs tests on push/PR:

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e .
      - run: pip install -r requirements.txt
      - run: pytest -q
```

**Risk:** None. Won't affect existing code or tests.

---

## Execution Order

```
Batch 1 (safe refactors)
  ├── AP-012: Remove unused import
  ├── AP-013: Add type hints  
  ├── AP-002: Deduplicate _get_i18n()
  ├── AP-004: Fix _video_to_card() duplicate
  └── AP-005: Already resolved by AP-004
  └── Run: pytest -q ✅

Batch 2 (behavior-preserving changes)
  ├── AP-008: Download HTMX locally
  ├── AP-009: Extract CSS to external file
  ├── AP-007: Fix 400→404 for clip source not found
  ├── AP-001: URL consistency (plural routes)
  └── Run: pytest -q ✅

Batch 3 (larger refactors)
  ├── AP-011: Extract clip test mock helpers
  ├── AP-006: Fix hardcoded test IDs
  ├── AP-003: Add pyproject.toml, remove sys.path hacks
  ├── AP-010: Add CI workflow
  └── Run: pytest -q ✅
```

## Error Handling

| Scenario | Safeguard |
|----------|-----------|
| Any batch breaks tests | Revert batch, fix, retry |
| AP-001 URL rename breaks links | Full grep for `/video/` in templates/ and static/ |
| AP-007 changes HTTP status | Update affected test assertions |
| AP-003 breaks imports | Keep old sys.path as fallback until verified |

## Testing Strategy

- Run `pytest -q` after each batch (3 runs total)
- 87 existing tests must pass after each batch (i18n tests included)
- For AP-001 (URL rename): manually verify all template links match new URL schema
- For AP-003 (package install): test both via pytest and direct `python -m app.main`

## Implementation Checklist

### Batch 1
- [ ] AP-012: Remove unused import from video_service.py
- [ ] AP-013: Add type hints to service functions
- [ ] AP-002: Deduplicate _get_i18n()
- [ ] AP-004/005: Fix _video_to_card() duplication
- [ ] Run tests: `pytest -q`

### Batch 2
- [ ] AP-008: Download HTMX locally
- [ ] AP-009: Extract CSS to external file
- [ ] AP-007: Fix 400→404 for clip source not found
- [ ] AP-001: Fix URL inconsistency
- [ ] Run tests: `pytest -q`

### Batch 3
- [ ] AP-011: Extract mock helpers
- [ ] AP-006: Fix hardcoded test IDs
- [ ] AP-003: Add pyproject.toml, remove sys.path hacks
- [ ] AP-010: Add CI workflow
- [ ] Run tests: `pytest -q`

## Open Questions

1. **AP-006 scope:** Should we fix ALL hardcoded IDs or just the ones in files we're touching? All is safer but doubles the change scope.

2. **AP-011 approach:** Accepting a reusable helper, or should we refactor clip_service to be more testable (e.g., inject mocks via function arguments)? The latter is better design but adds coupling to the service layer.
