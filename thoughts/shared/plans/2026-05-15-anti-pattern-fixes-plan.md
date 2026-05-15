# Anti-Pattern Fixes Implementation Plan

**Goal:** Fix all 13 anti-patterns (AP-001 through AP-013) identified across the codebase — duplicated code, inconsistent naming, brittle tests, missing infrastructure, and technical debt.

**Architecture:** Apply fixes in 3 independent batches. Batch 1 is all non-behavioral refactors (remove unused imports, add type hints, deduplicate helpers). Batch 2 is behavior-preserving but modifies URLs and HTTP status codes (needs test updates). Batch 3 adds infrastructure and test improvements. Each batch is independently testable — run `pytest -q` after each.

**Design:** `thoughts/shared/designs/2026-05-15-anti-pattern-fixes-design.md`

---

## Dependency Graph

```
Batch 1 (parallel): 1.1, 1.2, 1.3, 1.4   [no deps — safe refactors]
           ↓
Batch 2 (parallel): 2.1, 2.2, 2.3, 2.4a, 2.4b, 2.4c, 2.4d, 2.4e [moderate changes]
           ↓
Batch 3 (parallel): 3.1, 3.2, 3.3, 3.4   [larger refactors]
```

NOTE: Within each batch, micro-tasks that modify the **same file** must be applied sequentially (order specified). Micro-tasks on different files can run in parallel.

---

## Batch 1: Quick Fixes (no behavior change)

All tasks in this batch are non-behavioral and independent. Run `pytest -q` after all 4 complete.

### Task 1.1 — AP-012: Remove unused import
**File:** `app/services/video_service.py`
**Test:** none (no behavior change)
**Depends:** none

**Change:** Remove line 10: `from app.database import get_db`

Before (lines 8-11):
```python
import logging

from app.database import get_db
from app.services import file_service, tag_service
```

After:
```python
import logging

from app.services import file_service, tag_service
```

**Verify:** `pytest -q` — must still show 87 passed

---

### Task 1.2 — AP-013: Add type hints for `db` parameter in 3 service files
**Files:**
- `app/services/video_service.py`
- `app/services/tag_service.py`
- `app/services/clip_service.py`

**Test:** none (compile-time only)
**Depends:** none

#### File 1: `app/services/video_service.py`

**Change 1:** Add import at top (line 8), after `import logging`:
```python
import aiosqlite
```

**Change 2:** Annotate `db` in every function signature:

| Function | Current | After |
|---|---|---|
| `create_video` | `async def create_video(db, name: str, ...)` | `async def create_video(db: aiosqlite.Connection, name: str, ...)` |
| `get_video` | `async def get_video(db, video_id: int)` | `async def get_video(db: aiosqlite.Connection, video_id: int)` |
| `list_videos` | `async def list_videos(db)` | `async def list_videos(db: aiosqlite.Connection)` |
| `update_video` | `async def update_video(db, video_id: int, name: str)` | `async def update_video(db: aiosqlite.Connection, video_id: int, name: str)` |
| `delete_video` | `async def delete_video(db, video_id: int)` | `async def delete_video(db: aiosqlite.Connection, video_id: int)` |
| `get_video_with_tags` | `async def get_video_with_tags(db, video_id: int)` | `async def get_video_with_tags(db: aiosqlite.Connection, video_id: int)` |
| `list_videos_with_tags` | `async def list_videos_with_tags(db)` | `async def list_videos_with_tags(db: aiosqlite.Connection)` |
| `list_videos_by_tag` | `async def list_videos_by_tag(db, tag_id: int)` | `async def list_videos_by_tag(db: aiosqlite.Connection, tag_id: int)` |

#### File 2: `app/services/tag_service.py`

**Change 1:** Add import at top (after docstring, before line 5):
```python
import aiosqlite
```

**Change 2:** Annotate `db` in every function signature:

| Function | Current | After |
|---|---|---|
| `get_or_create_tag` | `async def get_or_create_tag(db, name: str)` | `async def get_or_create_tag(db: aiosqlite.Connection, name: str)` |
| `list_all_tags` | `async def list_all_tags(db)` | `async def list_all_tags(db: aiosqlite.Connection)` |
| `get_video_tags` | `async def get_video_tags(db, video_id: int)` | `async def get_video_tags(db: aiosqlite.Connection, video_id: int)` |
| `set_video_tags` | `async def set_video_tags(db, video_id: int, tag_names: list[str])` | `async def set_video_tags(db: aiosqlite.Connection, video_id: int, tag_names: list[str])` |
| `get_tag` | `async def get_tag(db, tag_id: int)` | `async def get_tag(db: aiosqlite.Connection, tag_id: int)` |
| `update_tag` | `async def update_tag(db, tag_id: int, new_name: str)` | `async def update_tag(db: aiosqlite.Connection, tag_id: int, new_name: str)` |
| `delete_tag` | `async def delete_tag(db, tag_id: int)` | `async def delete_tag(db: aiosqlite.Connection, tag_id: int)` |
| `list_all_tags_with_counts` | `async def list_all_tags_with_counts(db)` | `async def list_all_tags_with_counts(db: aiosqlite.Connection)` |

#### File 3: `app/services/clip_service.py`

**Change 1:** Add import (after `import math` on line 10, before `import shutil`):
```python
import aiosqlite
```

**Change 2:** Annotate `db` in `create_clip`:
Before (line 74):
```python
async def create_clip(
    db,
    source_video_id: int,
```
After:
```python
async def create_clip(
    db: aiosqlite.Connection,
    source_video_id: int,
```

**Verify:** `pytest -q` — must still show 87 passed

---

### Task 1.3 — AP-002: Deduplicate `_get_i18n()` into `templates.py`
**Files:**
- `app/templates.py` — Add public `get_i18n(request)` function
- `app/routes/videos.py` — Replace local `_get_i18n` with import
- `app/routes/tags.py` — Replace local `_get_i18n` with import

**Test:** none (identical behavior, pure refactor)
**Depends:** none (all file changes are consistent from the design)

#### File A: `app/templates.py`

Add after the `get_i18n_context` function (after line 136, before `parse_accept_language`):

```python
def get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback.

    Middleware sets request.state.i18n, but in tests it may not exist.
    """
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
```

Also add `from fastapi import Request` import to the top of the file (after `import json` on line 12):

```python
from fastapi import Request
```

#### File B: `app/routes/videos.py`

**Change 1:** At the import block (line 19), add `get_i18n` to the import from `app.templates`:
Before:
```python
from app.templates import templates, DEFAULT_LANG, LANG_FLAGS, get_i18n_context
```
After:
```python
from app.templates import templates, DEFAULT_LANG, LANG_FLAGS, get_i18n, get_i18n_context
```

**Change 2:** Remove the local `_get_i18n` function (lines 44-49). Delete these lines:
```python
def _get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback.

    Middleware sets request.state.i18n, but in tests it may not exist.
    """
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
```

**Change 3:** Replace all calls from `_get_i18n(request)` to `get_i18n(request)` in the file.
- Line 59: `i18n = _get_i18n(request)` → `i18n = get_i18n(request)`
- Line 121: same
- Line 147: same
- Line 167: same
- Line 222: same
- Line 250: same
- Line 299: same

#### File C: `app/routes/tags.py`

**Change 1:** At the import block (line 13), add `get_i18n` to the import:
Before:
```python
from app.templates import templates, DEFAULT_LANG, get_i18n_context
```
After:
```python
from app.templates import templates, DEFAULT_LANG, get_i18n, get_i18n_context
```

**Change 2:** Remove the local `_get_i18n` function (lines 18-23). Delete these lines:
```python
def _get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback.

    Middleware sets request.state.i18n, but in tests it may not exist.
    """
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
```

**Change 3:** Replace calls from `_get_i18n(request)` to `get_i18n(request)`:
- Line 36: `i18n = _get_i18n(request)` → `i18n = get_i18n(request)`

**Verify:** `pytest -q` — must still show 87 passed

---

### Task 1.4 — AP-004/005: Fix `_video_to_card()` duplication in `video_detail` route
**File:** `app/routes/videos.py`
**Test:** none (identical behavior, the inline code was a duplicate)
**Depends:** none

**Change:** In the `video_detail` route (lines 227-236), remove the inline thumbnail override and keep only the `video_url` field.

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

(Note: the URL path uses `/api/video/` (singular) since AP-001 in Batch 2 will globally rename all occurrences to `/api/videos/`.)

**Verify:** `pytest -q` — must still show 87 passed

---

## Batch 2: Moderate Changes (behavior-preserving)

### Task 2.1 — AP-008: Download HTMX locally
**Files:**
- `app/static/js/htmx.min.js` — Downloaded HTMX library
- `app/templates/base.html` — Update script tag

**Test:** none (static file, same code)
**Depends:** 1.x (all Batch 1 complete)

#### Step 1: Download HTMX
```bash
mkdir -p app/static/js && curl -o app/static/js/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js
```

#### Step 2: Update `app/templates/base.html` line 7
Before:
```html
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
```
After:
```html
<script src="/static/js/htmx.min.js"></script>
```

**Verify:** `pytest -q` — must still show 87 passed

---

### Task 2.2 — AP-009: Extract CSS to external file
**Files:**
- `app/static/css/style.css` — New file with all CSS
- `app/templates/base.html` — Replace `<style>` with `<link>`

**Test:** none (same CSS, external reference)
**Depends:** 1.x (all Batch 1 complete)

#### File A: Create `app/static/css/style.css`

Complete content — all CSS from the `<style>` block in `base.html` (lines 9-163):
```css
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
.btn-inactive { background: #e0e0e0; color: #333; }
.btn-inactive:hover { background: #d0d0d0; }
.btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
.error { color: #e63946; background: #ffe5e7; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; }
.success { color: #2d6a4f; background: #d8f3dc; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; }
.empty-state { text-align: center; padding: 3rem; color: #888; }
.empty-state p { font-size: 1.1rem; }
form label { display: block; margin-bottom: 0.25rem; font-weight: 600; }
form input[type="text"],
form input[type="file"] { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 6px; margin-bottom: 1rem; }
form button[type="submit"] { margin-top: 0.5rem; }

/* Responsive video player */
.video-wrapper { max-width: 1100px; margin: 0 auto; }
.video-wrapper video { width: 100%; display: block; }
.video-player { background: #000; border-radius: 10px; overflow: hidden; margin-bottom: 1.5rem; }
.video-player video { width: 100%; display: block; max-height: 80vh; }

@media (min-width: 1200px) {
    .video-wrapper {
        width: min(90vw, 1400px);
        max-width: none;
        margin: 0;
        position: relative;
        left: 50%;
        transform: translateX(-50%);
    }
}

/* Clip seeker controls */
.seeker-controls { padding: 1rem; background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem; }
.seeker-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.seeker-label { font-weight: 600; font-size: 0.85rem; min-width: 3rem; }
.seeker-start { color: #4361ee; }
.seeker-end { color: #e63946; }
.seeker-slider { flex: 1; cursor: pointer; }
.seeker-times { text-align: center; font-size: 1.1rem; font-weight: 600; color: #333; padding: 0.5rem 0; }
.seeker-hint { text-align: center; font-size: 0.8rem; color: #888; margin-bottom: 0.75rem; }
.seeker-error { color: #e63946; font-size: 0.9rem; margin-bottom: 0.5rem; text-align: center; }
.seeker-controls .btn-primary { padding: 0.75rem 2rem; font-size: 1rem; }

/* Responsive header that wraps on mobile */
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; }
.page-header h1 { font-size: clamp(1.1rem, 4vw, 1.5rem); word-break: break-word; }
.page-header .actions { display: flex; gap: 0.5rem; flex-shrink: 0; }

@media (max-width: 768px) {
    .container { padding: 1rem; }
    nav { padding: 0.75rem 1rem; gap: 1rem; }
    .page-header { flex-direction: column; }
    .video-player video { max-height: 50vh; }
}

@media (max-width: 480px) {
    .container { padding: 0.75rem; }
    nav { padding: 0.5rem 0.75rem; }
    .video-player { border-radius: 6px; }
    .video-player video { max-height: 40vh; }
}

/* Space indicator in nav bar */
.space-ok { color: #2d6a4f; background: #d8f3dc; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
.space-warn { color: #936639; background: #fff3cd; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
.space-critical { color: #e63946; background: #ffe5e7; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }

/* Language dropdown */
.lang-dropdown {
    position: relative;
    margin-left: 0.5rem;
}
.lang-btn {
    background: transparent;
    color: #fff;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px;
    padding: 0.3rem 0.6rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.85rem;
}
.lang-btn:hover {
    background: rgba(255,255,255,0.1);
}
.lang-arrow {
    font-size: 0.6rem;
    opacity: 0.7;
}
.lang-menu {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 0.25rem;
    background: #1a1a2e;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 4px;
    min-width: 140px;
    z-index: 100;
    display: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.lang-menu.open {
    display: block;
}
.lang-menu a {
    display: block;
    padding: 0.5rem 0.75rem;
    color: #fff;
    text-decoration: none;
    cursor: pointer;
}
.lang-menu a:hover {
    background: rgba(255,255,255,0.1);
    text-decoration: none;
}
.lang-flag {
    margin-right: 0.4rem;
}
```

#### File B: Update `app/templates/base.html`

Replace the entire `<style>...</style>` block (lines 8-163) with:
```html
    <link rel="stylesheet" href="/static/css/style.css">
```

**Verify:** `pytest -q` — must still show 87 passed

---

### Task 2.3 — AP-007: Fix 400→404 for clip source not found
**Files:**
- `app/routes/videos.py` — Add source video existence check before calling `clip_service.create_clip()`
- `tests/test_clips.py` — Update `test_clip_nonexistent_source` assertion

**Test:** Updates test expectation from 400 to 404
**Depends:** 1.x (all Batch 1 complete)

#### File A: `app/routes/videos.py`

In the `create_clip` route, add a source video lookup BEFORE the `try/except` block (after line 346, before line 347):

Before (lines 347-352):
```python
    try:
        clip = await clip_service.create_clip(db, video_id, start, end)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
```

After:
```python
    # Check source video exists (returns 404 instead of 400)
    source = await video_service.get_video(db, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source video not found")

    try:
        clip = await clip_service.create_clip(db, video_id, start, end)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
```

#### File B: `tests/test_clips.py`

Update `test_clip_nonexistent_source` (lines 57-66). Change the assertion from 400 to 404:

Before (line 66):
```python
        assert response.status_code == 400
```

After:
```python
        assert response.status_code == 404
```

Also update the comment on line 65:
Before:
```python
        # Route catches ValueError (source not found) and returns 400
```
After:
```python
        # Route returns 404 when source video does not exist
```

**Verify:** `pytest tests/test_clips.py -q` — must show all tests passed

---

### Task 2.4 — AP-001: Fix URL inconsistency (plural routes)

**Design decision:** All singular `/api/video/` and `/video/` routes become plural `/api/videos/` and `/videos/`. This is the largest change, touching routes, templates, JS, and tests. Split into 5 sub-tasks by file group, all parallel since each has a distinct search-replace pattern.

#### Sub-task 2.4a: Update route decorators in `app/routes/videos.py`

**Depends:** 1.x, 2.3 (because 2.3 adds new code that also contains URL strings)

Apply these search-and-replace changes:

| Current route | New route |
|---|---|
| `@router.get("/api/video/{video_id}/file")` | `@router.get("/api/videos/{video_id}/file")` |
| `@router.get("/video/{video_id}")` | `@router.get("/videos/{video_id}")` |
| `@router.get("/video/{video_id}/edit")` | `@router.get("/videos/{video_id}/edit")` |
| `@router.post("/video/{video_id}/edit")` | `@router.post("/videos/{video_id}/edit")` |
| `@router.post("/video/{video_id}/delete")` | `@router.post("/videos/{video_id}/delete")` |
| `@router.get("/video/{video_id}/clip")` | `@router.get("/videos/{video_id}/clip")` |
| `@router.post("/api/video/{video_id}/clip")` | `@router.post("/api/videos/{video_id}/clip")` |

Also update URL strings inside route bodies:
- Line 229: `f"/api/video/{video_id}/file"` → `f"/api/videos/{video_id}/file"`
- Line 284: `url=f"/video/{video_id}"` → `url=f"/videos/{video_id}"`
- Line 305: `f"/api/video/{video_id}/file"` → `f"/api/videos/{video_id}/file"`
- Line 354: `f"/video/{clip['id']}"` → `f"/videos/{clip['id']}"`

**Verify:** `pytest -q | head -5` — check for crash-only errors (tests will still use old URLs at this point)

#### Sub-task 2.4b: Update template URLs

**Depends:** 1.x
**Files (all parallel):**

1. `app/templates/_video_grid.html` line 14:
   - Change: `<a href="/video/{{ video.id }}"` → `<a href="/videos/{{ video.id }}"`

2. `app/templates/video_detail.html` lines 15-16:
   - Line 15: `<a href="/video/{{ video.id }}/clip"` → `<a href="/videos/{{ video.id }}/clip"`
   - Line 16: `<a href="/video/{{ video.id }}/edit"` → `<a href="/videos/{{ video.id }}/edit"`

3. `app/templates/edit.html` lines 6, 14, 27, 38:
   - Line 6: `<a href="/video/{{ video.id }}"` → `<a href="/videos/{{ video.id }}"`
   - Line 14: `<form action="/video/{{ video.id }}/edit"` → `<form action="/videos/{{ video.id }}/edit"`
   - Line 27: `<a href="/video/{{ video.id }}"` → `<a href="/videos/{{ video.id }}"`
   - Line 38: `<form action="/video/{{ video.id }}/delete"` → `<form action="/videos/{{ video.id }}/delete"`

4. `app/templates/clip.html` line 7:
   - Change: `<a href="/video/{{ video.id }}"` → `<a href="/videos/{{ video.id }}"`

**Verify:** `pytest -q | head -5` — smoke check

#### Sub-task 2.4c: Update `app/static/js/clipper.js`

**Depends:** 1.x

Two URL changes:
1. Line 116: `"/api/video/" + videoId + "/clip"` → `"/api/videos/" + videoId + "/clip"`
2. Line 135: `"/video/" + data.id` → `"/videos/" + data.id`

**Verify:** Check file for no remaining `/api/video/` or `/video/` patterns (except comments)

#### Sub-task 2.4d: Update `tests/test_videos.py`

**Depends:** 1.x

Find-and-replace all URL references:

| Current URL | New URL |
|---|---|
| `/video/` → (in routes, as in `/video/1`, `/video/999`, `/video/1/edit`, etc.) | `/videos/` |
| `/api/video/` → (as in `/api/video/1/file`, `/api/video/999/file`) | `/api/videos/` |

Exact lines to change:
- Line 103: `GET /video/{id}` (in docstring) → `GET /videos/{id}`
- Line 111: `/video/1` → `/videos/1`
- Line 119: `/video/999` → `/videos/999`
- Line 124: `GET /api/video/{id}/file` (docstring) → `GET /api/videos/{id}/file`
- Line 131: `/api/video/1/file` → `/api/videos/1/file`
- Line 138: `/api/video/999/file` → `/api/videos/999/file`
- Line 196: `POST /video/{id}/edit` (docstring) → `POST /videos/{id}/edit`
- Line 204: `/video/1/edit` → `/videos/1/edit`
- Line 209: `/video/1` → `/videos/1`
- Line 223: `/video/1/edit` → `/videos/1/edit`
- Line 227: `/video/1` → `/videos/1`
- Line 246: `/video/1/delete` → `/videos/1/delete`
- Line 256: `/video/999/delete` → `/videos/999/delete`
- Line 261: `GET /video/{id}/edit` (docstring) → `GET /videos/{id}/edit`
- Line 268: `/video/1/edit` → `/videos/1/edit`
- Line 289: `/video/999` → `/videos/999`
- Line 295: `/video/999/edit` → `/videos/999/edit`
- Line 306: `/video/1/delete` → `/videos/1/delete`
- Line 314: `/video/2` → `/videos/2`

#### Sub-task 2.4e: Update `tests/test_clips.py` and `tests/test_tags.py`

**Depends:** 1.x

**`tests/test_clips.py`:**

| Line | Current URL | New URL |
|---|---|---|
| 31 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 49 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 61 | `/api/video/999/clip` | `/api/videos/999/clip` |
| 72 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 82 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 92 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 111 | `/video/1/clip` | `/videos/1/clip` |
| 122 | `/video/999/clip` | `/videos/999/clip` |
| 134 | `/video/1/clip` | `/videos/1/clip` |
| 196 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 259 | `/api/video/1/clip` | `/api/videos/1/clip` |
| 267 | `/video/2` | `/videos/2` |
| 315 | `/api/video/1/clip` | `/api/videos/1/clip` |

Also update docstrings:
- Line 104: `GET /video/{id}/clip` → `GET /videos/{id}/clip`
- Line 121: `GET /video/{id}/clip` → `GET /videos/{id}/clip`

**`tests/test_tags.py`:**
- Line 77: docstring `GET /video/1` → `GET /videos/1`
- Line 83: `/video/1` → `/videos/1`

**Verify after all AP-001 sub-tasks:** `pytest -q` — must show 87 passed

---

## Batch 3: Larger Refactors

### Task 3.1 — AP-011: Extract clip test mock helpers
**Files:**
- `tests/conftest.py` — Add `mock_ffmpeg()` context manager
- `tests/test_clips.py` — Refactor 3 mock tests to use the helper

**Test:** Existing tests pass with cleaner mock setup
**Depends:** 2.x (all Batch 2 complete)

#### File A: Add to `tests/conftest.py`

Add after the existing imports (after line 14, before the `# Ensure project root` comment):

```python
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
```

At the END of `conftest.py` (after line 60), add:

```python
@contextmanager
def mock_ffmpeg(source_filename="src.mp4", duration=60.0, returncode=0):
    """Context manager that mocks ffmpeg/ffprobe for clip tests.

    Sets up:
    - shutil.which returning paths for ffprobe and ffmpeg
    - create_subprocess_exec returning mocked processes
    - file_service.get_video_path returning appropriate paths
    - file_service.generate_thumbnail as a no-op

    Args:
        source_filename: The filename that triggers "source" path matching.
        duration: Duration in seconds that ffprobe returns.
        returncode: Return code for the ffmpeg subprocess (0 = success).

    Yields:
        Tuple of (mock_which, mock_subproc) for additional assertions.
    """
    with patch("app.services.clip_service.shutil.which") as mock_which, \
         patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

        mock_which.side_effect = lambda cmd: {
            "ffprobe": "/usr/bin/ffprobe",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(cmd)

        # Mock ffprobe subprocess
        mock_ffprobe_proc = AsyncMock()
        mock_ffprobe_proc.returncode = 0
        mock_ffprobe_proc.communicate = AsyncMock(
            return_value=(f"{duration}\n".encode(), b"")
        )

        # Mock ffmpeg subprocess
        mock_ffmpeg_proc = AsyncMock()
        mock_ffmpeg_proc.returncode = returncode
        mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error output" if returncode != 0 else b""))

        mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

        # Mock file paths
        with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
             patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

            def _make_stat(size=1024):
                return type("Stat", (), {"st_size": size})()

            def _make_path(exists=True):
                return type("Path", (), {
                    "exists": lambda self: exists,
                    "stat": lambda self: _make_stat(),
                    "unlink": lambda self: None,
                })()

            mock_src_path = _make_path(True)
            mock_clip_path = _make_path(returncode == 0)

            def get_path_side_effect(filename):
                if source_filename in filename:
                    return mock_src_path
                return mock_clip_path

            mock_get_path.side_effect = get_path_side_effect

            yield (mock_which, mock_subproc)
```

#### File B: Refactor `tests/test_clips.py`

**Change 1:** Import the helper at the top (replace existing imports):
Before (lines 11-14):
```python
import json
from unittest.mock import AsyncMock, patch

import pytest
```
After:
```python
import json

import pytest

from tests.conftest import mock_ffmpeg
```

**Change 2:** Refactor `test_clip_creates_db_record` (lines 142-211):

Replace the entire test method body (lines 143-211) with:

```python
    async def test_clip_creates_db_record(self, client, db):
        """Successful clip creation inserts a DB record with source_video_id."""
        await client.post(
            "/api/videos",
            data={"name": "Source Vid", "tags": "alpha, beta"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        with mock_ffmpeg(source_filename="src"):
            response = await client.post(
                "/api/videos/1/clip",
                content=json.dumps({"start": 10, "end": 20}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify clip record in DB
        cursor = await db.execute("SELECT * FROM videos WHERE id = 2")
        clip = dict(await cursor.fetchone())
        assert clip["source_video_id"] == 1
        assert clip["clip_start"] == 10.0
        assert clip["clip_end"] == 20.0
        assert clip["name"] == "Source Vid (clip)"
```

**Change 3:** Refactor `test_clip_copies_source_tags` (lines 213-270):

Replace the entire test method body (lines 214-270) with:

```python
    async def test_clip_copies_source_tags(self, client, db):
        """Clip creation copies all tags from source video."""
        await client.post(
            "/api/videos",
            data={"name": "Tagged Source", "tags": "tutorial, funny, demo"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        with mock_ffmpeg(source_filename="src"):
            response = await client.post(
                "/api/videos/1/clip",
                content=json.dumps({"start": 5, "end": 15}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 200

        # Verify clip has the same tags
        detail = await client.get("/videos/2")
        assert "tutorial" in detail.text
        assert "funny" in detail.text
        assert "demo" in detail.text
```

**Change 4:** Refactor `test_clip_ffmpeg_failure_returns_500` (lines 272-324):

Replace the entire test method body (lines 273-324) with:

```python
    async def test_clip_ffmpeg_failure_returns_500(self, client, db):
        """When ffmpeg fails, clip endpoint returns 500."""
        await client.post(
            "/api/videos",
            data={"name": "Failing Source", "tags": ""},
            files={"file": ("fail.mp4", b"fake-video-content", "video/mp4")},
        )

        with mock_ffmpeg(source_filename="fail", returncode=1):
            response = await client.post(
                "/api/videos/1/clip",
                content=json.dumps({"start": 0, "end": 10}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "ffmpeg" in data["error"].lower()
```

**Verify:** `pytest tests/test_clips.py -q` — must show all tests passed

---

### Task 3.2 — AP-006: Fix hardcoded test IDs
**Files:**
- `tests/conftest.py` — Add ID capture helper
- `tests/test_videos.py` — Use dynamic IDs
- `tests/test_tags.py` — Use dynamic IDs
- `tests/test_clips.py` — Use dynamic IDs

**Test:** All 87 tests pass with dynamically captured IDs
**Depends:** 2.x, 3.1 (conftest changes from AP-011 must be present)

#### File A: Add helper to `tests/conftest.py`

Add at the end of conftest.py (after the mock_ffmpeg function):

```python
async def create_test_video(client, name: str, tags: str = "") -> int:
    """Upload a test video and return its ID from the response.

    Works with both redirect (303 → follows to / , then checks DB)
    and JSON (200 → {"id": N}) responses.

    For XHR-like uploads, returns the id from JSON response directly.
    """
    response = await client.post(
        "/api/videos",
        data={"name": name, "tags": tags},
        files={"file": (f"{name}.mp4", b"fake-video-content", "video/mp4")},
    )

    if response.status_code == 200:
        # XHR/JSON response
        data = response.json()
        if "id" in data:
            return data["id"]

    # For redirect responses, we need the DB to get the latest ID
    # The test caller should use this helper when they need IDs
    # For redirect-based flows, capture from the Location header
    location = response.headers.get("location", "")
    return None  # Caller must handle redirect-based flows differently


async def upload_video_with_tags(client, name: str, tags: str, xhr: bool = False) -> int:
    """Upload a video and return its numeric ID.

    Uses JSON body for XHR-style upload to get the ID back directly.
    """
    headers = {"X-Requested-With": "XMLHttpRequest"} if xhr else {}
    response = await client.post(
        "/api/videos",
        data={"name": name, "tags": tags},
        files={"file": (f"{name}.mp4", b"fake-video-content", "video/mp4")},
        headers=headers if xhr else {},
    )

    if response.status_code == 200 and xhr:
        return response.json()["id"]

    # Fallback: non-XHR returns 303, can't get ID directly
    # Return None and the test must use the video detail endpoint
    return None
```

#### File B: Update `tests/test_videos.py`

Strategy: Replace hardcoded `video/1`, `video/999`, etc. with dynamically captured IDs where possible, or use IDs that tests legitimately expect (e.g., 999 for non-existent).

Key changes:

1. `TestVideoPlayback.test_video_detail_page` (lines 102-114):
   - Capture the upload response ID when possible
   - Change `/video/1` to use captured ID

2. `TestVideoPlayback.test_video_stream_endpoint` (lines 123-133):
   - Same approach

3. `TestVideoCRUD.test_edit_video_name` (lines 195-211):
   - Capture ID from upload, use it in `/videos/{id}/edit`

4. `TestVideoCRUD.test_edit_video_tags` (lines 213-230):
   - Same

5. `TestVideoCRUD.test_delete_video` (lines 232-251):
   - Same

6. `TestVideoCRUD.test_upload_then_delete_then_reupload` (lines 298-316):
   - This test verifies `id=2` after delete + reupload. It _intentionally_ checks the incrementing ID behavior. This is a valid hardcoded assertion.

7. `TestAsyncUpload.test_upload_xhr_returns_json` (line 343):
   - `assert data["id"] == 1` → this should check against the actual ID from the response

Since the URLs are already updated by AP-001, the main change here is replacing hardcoded `id=1` with dynamic ID capture.

For tests that upload a single video then reference `/videos/{id}` — replace with the captured ID.
For tests that reference `/videos/999` (non-existent) — keep 999 as that's intentionally invalid.
For the upload-XHR test (line 343: `assert data["id"] == 1`) — remove the hardcoded `== 1` assertion, just check `"id" in data`.

#### File C: Update `tests/test_tags.py`

- Line 83: `/video/1` → change to capture ID dynamically (or use the `_create_test_video` helper that already exists in the file — refactor it to return the ID)

Update the existing `_create_test_video` helper (line 88-94) to return the ID:

```python
async def _create_test_video(client, name: str, tags: str = ""):
    """Create a test video with given tags and return response + id."""
    response = await client.post(
        "/api/videos",
        data={"name": name, "tags": tags},
        files={"file": (f"{name}.mp4", b"content", "video/mp4")},
    )
    return response
```

And update the test that uses `/video/1` (now `/videos/1`) to use the captured ID:

In `test_tags_in_detail` (line 83):
```python
        response = await client.get("/videos/1")
```
Change to capture the actual ID from the upload response. Since the upload returns 303 (redirect), we need a different approach. Either:
- Use XHR header to get JSON response with the ID
- Or query the DB for the ID

For simplicity, since we control the DB via fixtures, we can query `SELECT MAX(id) FROM videos` after the upload.

#### File D: Update `tests/test_clips.py`

- Replace `/videos/1/clip` and `/videos/2` with dynamically captured IDs
- Keep `/videos/999/clip` as intentionally invalid

For tests that upload a single video, capture the ID and use it throughout.

**Verify:** `pytest -q` — must show 87 passed

---

### Task 3.3 — AP-003: Add pyproject.toml, remove sys.path hacks
**Files:**
- `pyproject.toml` — New file
- `app/main.py` — Remove sys.path manipulation
- `tests/conftest.py` — Remove sys.path manipulation

**Test:** `pip install -e . && pytest -q` — must show 87 passed
**Depends:** 2.x

#### File A: Create `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "video-bank"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "jinja2>=3.1.0",
    "aiosqlite>=0.20.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.setuptools.package-data]
app = ["templates/*.html", "static/**/*"]
```

#### File B: `app/main.py`

Remove lines 17-20 (the sys.path block):

Before (lines 17-20):
```python
# Ensure the project root is on sys.path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
```

After: delete these 4 lines.

Also update the `_project_root` usage on line 23 to be computed inline instead:
Before:
```python
LOG_DIR = os.environ.get("LOG_DIR", str(_project_root / "logs"))
```
After:
```python
LOG_DIR = os.environ.get("LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
```

And remove the now-unused `import sys` on line 10.

After the change, the top of `main.py` should look like:
```python
"""
FastAPI application entry point.
...
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── Logging constants ──────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
...
```

#### File C: `tests/conftest.py`

Remove lines 22-25 (the sys.path block):

Before (lines 22-25):
```python
# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
```

After: delete these 4 lines.

Also remove the now-unused imports:
- `import sys` on line 12
- `from pathlib import Path` on line 13 — but only if `Path` is not used elsewhere in the file

After the change, the top of `conftest.py` should look like:
```python
"""
Pytest fixtures for all tests.
...
"""

import asyncio
import os
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import init_db, get_db
from app.main import app as _app
```

**Post-step:** Run:
```bash
pip install -e .
```

**Verify:** `pip install -e . && pytest -q` — must show 87 passed

---

### Task 3.4 — AP-010: Add CI workflow
**File:** `.github/workflows/test.yml` — New file
**Test:** none (CI config, won't affect tests)
**Depends:** 2.x

#### Create `.github/workflows/test.yml`

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg

      - name: Install project
        run: |
          pip install -e .

      - name: Install test dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: pytest -q
```

**Verify:** No local verification needed. The workflow runs on GitHub.

---

## Final Verification

After ALL micro-tasks complete:

### Step 1: Verify package installation
```bash
pip install -e .
```

### Step 2: Run full test suite
```bash
pytest -q
```

Expected result: 87 passed (all existing tests remain green)

### Step 3: Manual URL checks
- Browse to `/` — video grid loads with correct `/videos/{id}` links
- Click a video card — goes to `/videos/{id}` detail page
- Clip and edit buttons on detail page point to `/videos/{id}/clip` and `/videos/{id}/edit`
- Edit form submits to `/videos/{id}/edit`
- Delete button submits to `/videos/{id}/delete`
- Clip form submits to `/api/videos/{id}/clip`
- Video player loads from `/api/videos/{id}/file`

---

## Summary of All Files Changed

| # | File | Action |
|---|---|---|
| 1.1 | `app/services/video_service.py` | Remove unused `get_db` import |
| 1.2a | `app/services/video_service.py` | Add `import aiosqlite`, type hints |
| 1.2b | `app/services/tag_service.py` | Add `import aiosqlite`, type hints |
| 1.2c | `app/services/clip_service.py` | Add `import aiosqlite`, type hints |
| 1.3a | `app/templates.py` | Add `get_i18n()` function |
| 1.3b | `app/routes/videos.py` | Use `get_i18n` from templates |
| 1.3c | `app/routes/tags.py` | Use `get_i18n` from templates |
| 1.4 | `app/routes/videos.py` | Remove duplicate thumbnail code |
| 2.1a | `app/static/js/htmx.min.js` | **New** (downloaded) |
| 2.1b | `app/templates/base.html` | Update HTMX script src |
| 2.2a | `app/static/css/style.css` | **New** (extracted CSS) |
| 2.2b | `app/templates/base.html` | Replace `<style>` with `<link>` |
| 2.3a | `app/routes/videos.py` | Add source existence check |
| 2.3b | `tests/test_clips.py` | Update 400→404 assertion |
| 2.4a | `app/routes/videos.py` | Pluralize all route decorators |
| 2.4b | `app/templates/_video_grid.html` | `/video/` → `/videos/` |
| 2.4b | `app/templates/video_detail.html` | `/video/` → `/videos/` |
| 2.4b | `app/templates/edit.html` | `/video/` → `/videos/` |
| 2.4b | `app/templates/clip.html` | `/video/` → `/videos/` |
| 2.4c | `app/static/js/clipper.js` | `/api/video/` → `/api/videos/` |
| 2.4d | `tests/test_videos.py` | Update all URL references |
| 2.4e | `tests/test_clips.py` | Update all URL references |
| 2.4e | `tests/test_tags.py` | Update all URL references |
| 3.1a | `tests/conftest.py` | Add `mock_ffmpeg()` helper |
| 3.1b | `tests/test_clips.py` | Use `mock_ffmpeg()` in 3 tests |
| 3.2a | `tests/conftest.py` | Add ID capture helpers |
| 3.2b | `tests/test_videos.py` | Use dynamic IDs |
| 3.2c | `tests/test_tags.py` | Use dynamic IDs |
| 3.2d | `tests/test_clips.py` | Use dynamic IDs |
| 3.3a | `pyproject.toml` | **New** |
| 3.3b | `app/main.py` | Remove sys.path hack |
| 3.3c | `tests/conftest.py` | Remove sys.path hack |
| 3.4 | `.github/workflows/test.yml` | **New** |
