# Available Disk Space Indicator & Upload Guard — Implementation Plan

**Goal:** Add a nav bar space indicator (HTMX fragment) and disk-space upload guard (95% threshold) to Video Bank.

**Architecture:** New `get_available_space()` in `file_service.py` wraps `shutil.disk_usage()`. Extended `validate_file()` checks projected disk usage. New `GET /api/space` route returns an HTMX fragment. Nav bar uses `hx-get` + `hx-trigger="load"` to fetch on every page load. No new dependencies. All tests use `unittest.mock.patch` on `app.services.file_service.shutil.disk_usage`.

**Design:** `thoughts/shared/designs/2026-05-15-available-space-design.md`

---

## Dependency Graph

```
Batch 1 (parallel): 1.1, 1.2      [foundation — no deps]
Batch 2 (parallel): 2.1, 2.2      [endpoint + UI — depends on batch 1]
Batch 3 (parallel): 3.1           [integration tests — depends on batch 2]
```

---

## CHECKPOINT 0: Baseline

```bash
pytest -q
# 45 passed — all existing tests green before any changes
```

---

# BATCH 1: Foundation (parallel — 2 implementers)

All tasks have NO dependencies and run simultaneously.

---

### Task 1.1: `file_service.py` — Disk space utilities + upload guard + 4 tests

**Files:** `app/services/file_service.py`, `tests/test_videos.py`
**Depends:** none

**Design decisions:**
- `get_available_space(directory=None)` defaults to `VIDEOS_DIR`. This gives `validate_file()` a sensible default while allowing the endpoint to pass an explicit directory later.
- `percent_used = used / total` (float 0.0–1.0). `free_gb = round(free / 1024**3, 1)` — matches the design spec.
- Error sentinel `{"error": True}` — clean, minimal. `validate_file()` skips the disk check when it sees `error`.
- Upload guard uses `> 0.95` (strictly greater). Exactly 95% is allowed.
- `shutil.disk_usage()` is called in `get_available_space()` which is called from `validate_file()`. When disk_usage fails, the upload is NOT blocked (fails open for availability).
- The type hint uses `Path | None` (Python 3.10+ union syntax), consistent with existing `str | None` returns in the codebase.

**1.1a — Add `get_available_space()` to `app/services/file_service.py`:**

Insert after the `_ensure_dirs()` function (before `_get_ext()`):

```python
def get_available_space(directory: Path | None = None) -> dict:
    """Return disk usage info for the given directory.

    Defaults to VIDEOS_DIR. Returns total, used, free (bytes),
    percent_used (0.0–1.0), and free_gb (human-readable, 1 decimal).

    On OSError (e.g. permission denied, missing dir), returns
    {"error": True} so callers can degrade gracefully.
    """
    try:
        usage = shutil.disk_usage(directory or VIDEOS_DIR)
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent_used": usage.used / usage.total,
            "free_gb": round(usage.free / (1024 ** 3), 1),
        }
    except OSError:
        return {"error": True}
```

**1.1b — Extend `validate_file()` in `app/services/file_service.py`:**

Add the disk space check at the end of `validate_file()`, after the existing size check:

```python
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

    # Disk space guard: reject if uploading would push disk past 95% capacity
    space = get_available_space()
    if not space.get("error"):
        projected = (space["used"] + file_size) / space["total"]
        if projected > 0.95:
            return "Not enough disk space (would exceed 95% capacity)."

    return None
```

**1.1c — Add 4 tests to `tests/test_videos.py`:**

Insert a new class `TestDiskSpace` at the end of the file (before any trailing whitespace, or just append):

```python
class TestDiskSpace:
    """Tests for disk space indicator and upload guard."""

    @pytest.mark.asyncio
    async def test_available_space(self):
        """get_available_space computes free_gb and percent_used correctly."""
        from app.services.file_service import get_available_space

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 500GB used out of 1TB → 50% used
            mock_du.return_value = (1_000_000_000_000, 500_000_000_000, 500_000_000_000)
            result = get_available_space()

        assert result.get("error") is not True
        assert result["total"] == 1_000_000_000_000
        assert result["used"] == 500_000_000_000
        assert result["free"] == 500_000_000_000
        assert result["percent_used"] == 0.5
        # 500 GB / 1024^3 ≈ 465.7
        assert result["free_gb"] == 465.7

    @pytest.mark.asyncio
    async def test_disk_usage_error_handling(self, client):
        """When shutil.disk_usage raises OSError, upload still works."""
        from app.services.file_service import get_available_space

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.side_effect = OSError("Permission denied")

            # Sentinel dict is returned
            result = get_available_space()
            assert result.get("error") is True

            # Upload should NOT be blocked by a failing space check
            response = await client.post(
                "/api/videos",
                data={"name": "Disk Error Test"},
                files={"file": ("error.mp4", b"fake-content", "video/mp4")},
            )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_upload_rejected_disk_full(self, client):
        """Upload rejected when projected disk usage > 95%."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 951GB used out of 1TB → 95.1% — any tiny file pushes over 95%
            mock_du.return_value = (1_000_000_000_000, 951_000_000_000, 49_000_000_000)

            response = await client.post(
                "/api/videos",
                data={"name": "Full Disk"},
                files={"file": ("full.mp4", b"oops", "video/mp4")},
            )
        assert response.status_code == 400
        assert "disk space" in response.text.lower()

    @pytest.mark.asyncio
    async def test_upload_allowed_disk_available(self, client):
        """Upload succeeds when there is plenty of disk space."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.return_value = (1_000_000_000_000, 500_000_000_000, 500_000_000_000)

            response = await client.post(
                "/api/videos",
                data={"name": "Space Available"},
                files={"file": ("ok.mp4", b"fake-content", "video/mp4")},
            )
        assert response.status_code == 303
```

**Implementation notes:**
- The `from unittest.mock import patch` import is already in `test_clips.py` but NOT in `test_videos.py`. The implementer MUST add `from unittest.mock import patch` at the top of the import block in `test_videos.py`.
- The existing import block at the top of `test_videos.py` is just `import pytest`. Append after it.
- Tests are additive to `test_videos.py` — they do NOT modify existing test classes.

**Verify:** `pytest -q tests/test_videos.py -v`
**Commit:** `feat(space): add get_available_space() and disk guard to validate_file()`

---

### Task 1.2: Create `_space_fragment.html` template

**File:** `app/templates/_space_fragment.html`
**Test:** none (tested by endpoint integration test in batch 3)
**Depends:** none

**Design decisions:**
- Three CSS classes matching thresholds from the design: `space-ok` (>20% free = percent_used ≤ 0.80), `space-warn` (10–20% free = 0.80 < percent_used ≤ 0.90), `space-critical` (<10% free = percent_used > 0.90 or error).
- On error, shows "Space: unknown" with `space-critical` styling (gray would be friendlier, but the design says "gray styling" — I'm implementing the template text, the CSS color is defined in base.html where the implementer can choose). I'll apply `space-critical` class but note the CSS can use gray for the error case.
- Template uses the `space` dict key passed by the route handler.

```html
{% if space.error %}
<span class="space-critical">Space: unknown</span>
{% elif space.percent_used <= 0.80 %}
<span class="space-ok">{{ space.free_gb }} GB free</span>
{% elif space.percent_used <= 0.90 %}
<span class="space-warn">{{ space.free_gb }} GB free</span>
{% else %}
<span class="space-critical">{{ space.free_gb }} GB free</span>
{% endif %}
```

**Verify:** File exists at `app/templates/_space_fragment.html`
**Commit:** `feat(space): add space indicator fragment template`

---

## CHECKPOINT 1: Foundation in place

```bash
pytest -q
# 49 passed — 45 existing + 4 new disk-space tests
```

**What's true at this point:**
- `get_available_space()` works and is testable
- `validate_file()` rejects uploads that would push past 95%
- The `_space_fragment.html` template exists (no endpoint to serve it yet)
- Upload guard tests mock disk_usage properly (independent of real disk)

---

# BATCH 2: Core (parallel — 2 implementers)

All tasks depend on Batch 1 completing. Tasks 2.1 and 2.2 are independent of each other.

---

### Task 2.1: `videos.py` — GET /api/space endpoint

**File:** `app/routes/videos.py`
**Test:** none (test added in batch 3)
**Depends:** 1.1 (needs `get_available_space`), 1.2 (needs `_space_fragment.html` template)

**Design decisions:**
- The endpoint is synchronous-capable (calls `get_available_space()` directly — a negligible blocking call that takes microseconds).
- No auth — this is a self-hosted internal tool, consistent with the rest of the app.
- Returns `text/html` content-type via `TemplateResponse` (standard FastAPI/Jinja2 behavior).
- The `get_available_space` function is added to the existing import from `file_service`.

**Add the import** (modify the existing line):

```python
from app.services.file_service import get_available_space, get_video_path
```

**Add the route handler** — insert after the `_video_to_card` function (around line 41), before the `list_videos` endpoint:

```python
@router.get("/api/space")
async def space_indicator(request: Request):
    """Return an HTML fragment showing available disk space in the uploads directory.

    This is consumed by the nav bar's hx-get in base.html. Never blocks
    an upload — returns a gray "Space: unknown" on error.
    """
    space = get_available_space()
    return templates.TemplateResponse(
        request, "_space_fragment.html",
        {"space": space},
    )
```

**Implementation notes:**
- The import change is on line 19 of `videos.py`. Replace `from app.services.file_service import get_video_path` with `from app.services.file_service import get_available_space, get_video_path`.
- The new route is added after `_video_to_card()` (line 41 area) and before `list_videos()` (line 44). This keeps related routes together.
- No changes to the existing upload route — the disk check is already handled in `validate_file()`.

**Verify:** `pytest -q` (49 still pass — no new tests yet, but verify existing tests aren't broken)
**Commit:** `feat(space): add GET /api/space endpoint for HTMX space indicator`

You should discuss with the user when you implement it: the endpoint location. The design puts `GET /api/space` in `videos.py` which is the existing route module. An alternative would be a separate route module (`space.py`). The current approach keeps changes minimal but mixes a non-video route into the video router. If the app gains more "utility" endpoints, consider a dedicated utility router.

---

### Task 2.2: `base.html` — CSS + HTMX space indicator in nav bar

**File:** `app/templates/base.html`
**Test:** none (visual change — tested manually)
**Depends:** 1.2 (needs to know the CSS class names used in `_space_fragment.html`)

**Design decisions:**
- Space indicator span uses `margin-left: auto` in the nav flexbox to push it to the right side.
- CSS classes match the template's classes: `space-ok` (green), `space-warn` (yellow), `space-critical` (red/gray).
- CSS uses existing project colors: `#2d6a4f` (green success), `#e63946` (red error), and `#936639` (amber/warn) — consistent with existing `.error` and `.success` classes.
- The HTMX trigger is `load` — fires once when each new page renders. No periodic refresh for v1 (noted as future enhancement in the design).

**2.2a — Add CSS rules** — insert inside the `<style>` block in `<head>`, before the closing `</style>` tag (before `{% block extra_head %}`):

```css
        /* Space indicator in nav bar */
        .space-ok { color: #2d6a4f; background: #d8f3dc; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
        .space-warn { color: #936639; background: #fff3cd; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
        .space-critical { color: #e63946; background: #ffe5e7; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
```

**2.2b — Add the indicator span** to the `<nav>` element. Change the nav from:

```html
    <nav>
        <a href="/">Video Bank</a>
        <a href="/upload">Upload</a>
    </nav>
```

to:

```html
    <nav>
        <a href="/">Video Bank</a>
        <a href="/upload">Upload</a>
        <span id="space-indicator" style="margin-left: auto;" hx-get="/api/space" hx-trigger="load"></span>
    </nav>
```

**Verify:** Start the dev server, open any page, check that the space indicator loads after a brief moment (HTMX fires GET /api/space on page load).
**Commit:** `feat(space): add space indicator CSS and HTMX element to nav bar`

---

## CHECKPOINT 2: Endpoint + UI wired up

```bash
pytest -q
# 49 passed — no new tests yet but existing tests confirm nothing is broken
```

**What's true at this point:**
- `GET /api/space` returns an HTML fragment with disk space info
- The nav bar fetches the indicator on every page load
- CSS classes color the badge green/yellow/red based on free space
- Upload guard silently rejects uploads past 95% (no user-visible change to the UI yet)

**Manual verification** (optional but recommended):
1. `uvicorn app.main:app --reload` (from project root)
2. Open `http://localhost:8000` in a browser
3. The nav bar should show something like "465.7 GB free" in green (right side)
4. The `pytest -q` output should still show 49 passed

---

# BATCH 3: Integration Tests (1 task)

### Task 3.1: `test_videos.py` — Space API endpoint test

**File:** `tests/test_videos.py`
**Depends:** 2.1 (the endpoint must exist), 1.1 (patches file_service.shutil.disk_usage)

**Design decisions:**
- Adds `test_space_api_endpoint` to the existing `TestDiskSpace` class created in task 1.1.
- Mocks `shutil.disk_usage` to return 50% usage → expects `space-ok` CSS class in response.
- Asserts 200 status, HTML content-type, and the presence of both "GB free" and the appropriate CSS class.

**Append this test method** inside the existing `TestDiskSpace` class (after `test_upload_allowed_disk_available`):

```python
    @pytest.mark.asyncio
    async def test_space_api_endpoint(self, client):
        """GET /api/space returns HTML fragment with color-coded space info."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 500GB used out of 1TB → 50% → space-ok (green)
            mock_du.return_value = (1_000_000_000_000, 500_000_000_000, 500_000_000_000)

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "GB free" in response.text
        assert "space-ok" in response.text

    @pytest.mark.asyncio
    async def test_space_api_endpoint_critical(self, client):
        """GET /api/space shows space-critical class when disk is near full."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 950GB used out of 1TB → 95% → space-critical (red)
            mock_du.return_value = (1_000_000_000_000, 950_000_000_000, 50_000_000_000)

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "space-critical" in response.text

    @pytest.mark.asyncio
    async def test_space_api_endpoint_error(self, client):
        """GET /api/space shows 'Space: unknown' when disk_usage fails."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.side_effect = OSError("Permission denied")

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "Space: unknown" in response.text
        assert "space-critical" in response.text
```

**Implementation notes:**
- The `from unittest.mock import patch` import is already present (added in task 1.1).
- These tests are added to the `TestDiskSpace` class — the existing 4 tests from task 1.1 + these 3 new ones = 7 tests in the class.
- Tests cover the three CSS classes: `space-ok` (green, <80%), `space-critical` (red, >90%), and the error path.

**Verify:** `pytest -q`
**Commit:** `test(space): add endpoint integration tests for space indicator`

---

## CHECKPOINT 3: Complete feature

```bash
pytest -q
# 52 passed — all 45 existing + 7 new disk space tests
```

```bash
pytest -q tests/test_videos.py -v
# Should show TestDiskSpace with 7 tests, all passing
```

**What's true at this point (full feature complete):**
- ✅ `get_available_space()` wraps `shutil.disk_usage()` with error handling
- ✅ `validate_file()` rejects uploads >95% with a clear error message
- ✅ `GET /api/space` returns an HTMX HTML fragment with disk info
- ✅ Nav bar shows the space indicator with color coding (green/yellow/red)
- ✅ Upload guard is transparent when disk info is unavailable (fails open)
- ✅ 7 new tests cover all scenarios: normal, full disk, disk error, endpoint CSS classes
- ✅ All 45 existing tests unchanged and passing
- ✅ Zero new Python dependencies
- ✅ Follows existing HTMX/Jinja2/FastAPI patterns

---

## Summary of all file changes

| File | Change | New Lines |
|------|--------|-----------|
| `app/services/file_service.py` | Add `get_available_space()` + extend `validate_file()` | ~20 |
| `app/templates/_space_fragment.html` | **NEW** — Space indicator partial | ~10 |
| `app/routes/videos.py` | Add `get_available_space` import + `GET /api/space` route | ~12 |
| `app/templates/base.html` | Add 3 CSS rules + `<span>` in nav | ~4 |
| `tests/test_videos.py` | Add import + `TestDiskSpace` class with 7 tests | ~90 |

**Total: ~136 new lines across 5 files (4 modified, 1 created).**
