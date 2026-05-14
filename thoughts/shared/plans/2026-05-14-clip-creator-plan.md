# Clip Creator + Async Upload Implementation Plan

**Goal:** Add async upload with progress popup and video clip creator to the Video Bank app.

**Architecture:** Vanilla JS + XMLHttpRequest for upload progress, HTML5 `<video>` API for clip seeker, ffmpeg subprocess for clip generation. No new runtime dependencies. Two independently testable checkpoints.

**Design:** `thoughts/shared/designs/2026-05-14-clip-creator-design.md`

---

## Dependency Graph

```
Checkpoint 1 ─────────────────────────────────────────────────
Batch 1 (parallel): 1.1, 1.2, 1.3   [foundation — no deps]
Batch 2 (parallel): 2.1, 2.2, 2.3, 2.4   [modifications — depends on batch 1]
Batch 3 (parallel): 3.1   [tests — depends on batch 2]

Checkpoint 2 ─────────────────────────────────────────────────
Batch 4 (parallel): 4.1, 4.2, 4.3   [core logic — no deps]
Batch 5 (parallel): 5.1, 5.2, 5.3, 5.4, 5.5   [modifications — depends on batch 4]
Batch 6 (parallel): 6.1   [tests — depends on batch 5]
```

---

# CHECKPOINT 1: Async Upload + Progress Popup

## Batch 1: Foundation Files (parallel — 3 implementers)

All tasks have NO dependencies and run simultaneously.

### Task 1.1: Create static package marker
**File:** `app/static/__init__.py`
**Test:** none (empty init)
**Depends:** none

```python
# Makes static a Python-aware directory (required for package resolution)
```

**Verify:** File exists at `app/static/__init__.py`
**Commit:** `chore(static): add static directory package init`

---

### Task 1.2: Upload JS — XHR with progress, popup management, sessionStorage persistence
**File:** `app/static/js/upload.js`
**Test:** none (JS behavior tested via integration in task 3.1)
**Depends:** none

Design decisions:
- Intercepts form `#upload-form` via `submit` event
- Creates XMLHttpRequest with `upload.onprogress` for real-time percentage
- Popup `<div id="upload-popup">` lives in DOM (from base.html include); JS just shows/hides it
- sessionStorage key `upload-active` holds `{filename, status}` for cross-navigation persistence
- On page load, checks sessionStorage and restores "Uploading..." state if upload was in-flight
- Popup states: `uploading` (animated bar), `completed` (green check), `failed` (red + retry button)
- Degrades gracefully if sessionStorage is full (upload still works, no persistence warning)

```javascript
/**
 * upload.js — Async upload with progress popup.
 *
 * Intercepts the upload form, creates an XHR with progress events,
 * and manages a bottom-left popup that persists across page navigations
 * via sessionStorage.
 */
(function () {
  "use strict";

  const UPLOAD_FORM_SELECTOR = "#upload-form";
  const POPUP_ID = "upload-popup";
  const STORAGE_KEY = "upload-active";

  // ── Popup helpers ──────────────────────────────────────────────

  /** Return the popup element, creating it if missing (defensive). */
  function getPopup() {
    let popup = document.getElementById(POPUP_ID);
    if (!popup) {
      popup = document.createElement("div");
      popup.id = POPUP_ID;
      popup.style.cssText =
        "position:fixed;bottom:1rem;left:1rem;z-index:9999;" +
        "background:#1a1a2e;color:#fff;padding:0.75rem 1rem;" +
        "border-radius:8px;min-width:280px;box-shadow:0 4px 12px rgba(0,0,0,0.3);" +
        "font-size:0.9rem;display:none;";
      document.body.appendChild(popup);
    }
    return popup;
  }

  function showPopup() {
    getPopup().style.display = "block";
  }

  function hidePopup() {
    getPopup().style.display = "none";
  }

  function setPopupContent(html) {
    getPopup().innerHTML = html;
  }

  // ── Progress bar HTML ──────────────────────────────────────────

  function progressBarHTML(pct) {
    const clamped = Math.min(100, Math.max(0, pct));
    return (
      '<div style="margin-top:6px;height:6px;background:#333;border-radius:3px;overflow:hidden;">' +
      '<div style="height:100%;width:' +
      clamped +
      '%;background:#4361ee;border-radius:3px;transition:width 0.2s;"></div>' +
      "</div>"
    );
  }

  // ── sessionStorage helpers ─────────────────────────────────────

  function saveState(filename, status) {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ filename: filename, status: status })
      );
    } catch (_) {
      // sessionStorage full — upload still works, just no persistence
    }
  }

  function clearState() {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (_) {
      // ignore
    }
  }

  function restoreState() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const state = JSON.parse(raw);
      if (state && state.filename) {
        showPopup();
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="flex:1;">' +
            escapeHtml(state.filename) +
            "</span>" +
            '<span style="color:#888;font-size:0.8rem;">' +
            (state.status === "completed"
              ? "&#10003; Done"
              : state.status === "failed"
                ? "&#10007; Failed"
                : "&#8987; Resumed") +
            "</span></div>" +
            (state.status === "uploading"
              ? progressBarHTML(0)
              : state.status === "failed"
                ? '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">Retry</button>'
                : "")
        );
      }
    } catch (_) {
      // ignore malformed state
    }
  }

  // ── Escaping ───────────────────────────────────────────────────

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Main upload handler ────────────────────────────────────────

  function handleUpload(event) {
    const form = event.target;
    const formData = new FormData(form);
    const filename =
      formData.get("file") && formData.get("file").name
        ? formData.get("file").name
        : "Untitled";

    event.preventDefault();

    const xhr = new XMLHttpRequest();
    const popup = getPopup();

    // ── Progress ──
    xhr.upload.addEventListener("progress", function (e) {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        showPopup();
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#888;font-size:0.8rem;">' +
            pct +
            "%</span></div>" +
            progressBarHTML(pct)
        );
        saveState(filename, "uploading");
      }
    });

    // ── Load / complete ──
    xhr.addEventListener("load", function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="color:#2d6a4f;">&#10003;</span>' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#2d6a4f;font-size:0.8rem;">Completed</span></div>'
        );
        saveState(filename, "completed");

        // Redirect to home after brief delay
        setTimeout(function () {
          clearState();
          window.location.href = "/";
        }, 1500);
      } else {
        // Server error
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="color:#e63946;">&#10007;</span>' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#e63946;font-size:0.8rem;">Failed</span></div>' +
            '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">Retry</button>'
        );
        saveState(filename, "failed");
      }
    });

    // ── Error / network failure ──
    xhr.addEventListener("error", function () {
      setPopupContent(
        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
          '<span style="color:#e63946;">&#10007;</span>' +
          '<span style="flex:1;">' +
          escapeHtml(filename) +
          "</span>" +
          '<span style="color:#e63946;font-size:0.8rem;">Network Error</span></div>' +
          '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">Retry</button>'
      );
      saveState(filename, "failed");
    });

    // ── Send ──
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.send(formData);
  }

  // ── Init ───────────────────────────────────────────────────────

  function init() {
    // Restore any in-flight upload popup
    restoreState();

    // Hook into the upload form
    const form = document.querySelector(UPLOAD_FORM_SELECTOR);
    if (form) {
      form.addEventListener("submit", handleUpload);
    }
  }

  // Wait for DOM to be ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

**Verify:** `ls app/static/js/upload.js`
**Commit:** `feat(upload): add async upload JS with progress popup`

---

### Task 1.3: Upload popup HTML fragment
**File:** `app/templates/_upload_popup.html`
**Test:** none (HTML fragment)
**Depends:** none

Note: The popup container is rendered here as an empty placeholder. The JS in `upload.js` manages its visibility and content dynamically. Base.html includes this fragment.

```html
<div id="upload-popup"
     style="position: fixed; bottom: 1rem; left: 1rem; z-index: 9999;
            background: #1a1a2e; color: #fff; padding: 0.75rem 1rem;
            border-radius: 8px; min-width: 280px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            font-size: 0.9rem; display: none;">
</div>
```

**Verify:** File exists at `app/templates/_upload_popup.html`
**Commit:** `feat(upload): add upload popup HTML fragment`

---

## Batch 2: Modify Existing Files (parallel — 4 implementers)

All tasks depend on Batch 1 files existing. They can run in parallel with each other since they modify different files.

### Task 2.1: Mount /static directory in FastAPI
**File:** `app/main.py`
**Test:** none (covered by integration test in task 3.1)
**Depends:** 1.1 (app/static/__init__.py exists)

Add the static directory mount after the uploads mount. Also update the startup migration version to 4 (needed for Checkpoint 2 but safe to do now since migration v4 is additive).

```python
# After the uploads mount (line 34), add:
# Mount static files (JS, CSS) at /static
static_dir = _project_root / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

**Edit to apply:**

Old (lines 28-34):
```python
# Mount static directories for uploaded files
uploads_dir = _project_root / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "videos").mkdir(parents=True, exist_ok=True)
(uploads_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
```

New:
```python
# Mount static directories for uploaded files
uploads_dir = _project_root / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "videos").mkdir(parents=True, exist_ok=True)
(uploads_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Mount static files (JS, CSS) at /static
static_dir = _project_root / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

**Verify:** `python -c "from app.main import app; print('OK')"`
**Commit:** `feat(static): mount /static directory for JS files`

---

### Task 2.2: Include upload popup and JS in base template
**File:** `app/templates/base.html`
**Test:** none (visual — verified by rendering)
**Depends:** 1.2 (upload.js), 1.3 (_upload_popup.html)

Add the popup include just before `</body>` and the upload.js script tag.

**Edit to apply:**

Old (line 66):
```html
</body>
</html>
```

New:
```html
    {% include "_upload_popup.html" %}
    <script src="/static/js/upload.js"></script>
</body>
</html>
```

**Verify:** Template renders without error
**Commit:** `feat(upload): include upload popup and JS in base template`

---

### Task 2.3: POST /api/videos returns JSON for XHR uploads
**File:** `app/routes/videos.py`
**Test:** none (covered by task 3.1)
**Depends:** none

Modify the `create_video` endpoint to check for `X-Requested-With: XMLHttpRequest` header. When present, return JSON `{"id": ..., "redirect": "/"}` instead of a 303 RedirectResponse. This lets the JS handler get the video ID and redirect client-side.

Add import for `JSONResponse` at the top.

**Edit to apply:**

Old imports (line 14):
```python
from fastapi.responses import FileResponse, RedirectResponse
```

New imports:
```python
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
```

Old `create_video` function (lines 78-107):
```python
@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form(""),  # Comma-separated tags
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
            tags=tags,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request, "upload.html",
            {"error": str(e)},
            status_code=400,
        )

    return RedirectResponse(url="/", status_code=303)
```

New `create_video` function:
```python
@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form(""),  # Comma-separated tags
    db=Depends(get_db),
):
    """Handle video upload. Redirects to list on success.
    
    When `X-Requested-With: XMLHttpRequest` is present, returns JSON
    instead of a redirect (for XHR uploads via upload.js).
    """
    # Read file content
    content = await file.read()

    try:
        video = await video_service.create_video(
            db,
            name=name,
            file_content=content,
            original_name=file.filename or "untitled",
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
            tags=tags,
        )
    except ValueError as e:
        # XHR requests get JSON errors too
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"error": str(e)}, status_code=400)
        return templates.TemplateResponse(
            request, "upload.html",
            {"error": str(e)},
            status_code=400,
        )

    # Return JSON for XHR uploads so JS can handle the response
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"id": video["id"], "redirect": "/"})

    return RedirectResponse(url="/", status_code=303)
```

**Verify:** `python -c "from app.routes.videos import router; print('OK')"`
**Commit:** `feat(upload): return JSON for XHR upload requests`

---

### Task 2.4: Add form ID for JS hooking
**File:** `app/templates/upload.html`
**Test:** none
**Depends:** none

Add `id="upload-form"` to the `<form>` tag so upload.js can intercept it.

**Edit to apply:**

Old (line 11):
```html
<form action="/api/videos" method="post" enctype="multipart/form-data">
```

New:
```html
<form id="upload-form" action="/api/videos" method="post" enctype="multipart/form-data">
```

**Verify:** Template renders with `id="upload-form"`
**Commit:** `feat(upload): add form ID for JS upload interception`

---

## Batch 3: Checkpoint 1 Tests (parallel — 1 implementer)

### Task 3.1: Add XHR upload tests
**File:** `tests/test_videos.py`
**Test:** self (adding test methods to existing test class)
**Depends:** 2.3 (XHR route changes)

Add tests:
- `test_upload_xhr_returns_json` — POST with `X-Requested-With: XMLHttpRequest` header returns JSON with video id
- `test_upload_xhr_error_returns_json` — XHR upload with bad data returns JSON error

Add a new test class `TestAsyncUpload` at the end of the file.

```python
class TestAsyncUpload:
    """Tests for XHR-based async upload (Checkpoint 1)."""

    @pytest.mark.asyncio
    async def test_upload_xhr_returns_json(self, client):
        """POST /api/videos with X-Requested-With returns JSON."""
        response = await client.post(
            "/api/videos",
            data={"name": "XHR Upload"},
            files={"file": ("xhr.mp4", b"fake-video-content", "video/mp4")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] == 1
        assert "redirect" in data
        assert data["redirect"] == "/"

    @pytest.mark.asyncio
    async def test_upload_xhr_bad_format(self, client):
        """XHR upload with unsupported format returns JSON error."""
        response = await client.post(
            "/api/videos",
            data={"name": "XHR Bad"},
            files={"file": ("bad.avi", b"content", "video/x-msvideo")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "unsupported" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_upload_xhr_missing_name(self, client):
        """XHR upload without name returns JSON error (422 from FastAPI)."""
        response = await client.post(
            "/api/videos",
            data={"name": ""},
            files={"file": ("no-name.mp4", b"content", "video/mp4")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # FastAPI's Form(...) returns 422 before our handler runs
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_upload_form_still_redirects(self, client):
        """Regular form upload still returns 303 redirect."""
        response = await client.post(
            "/api/videos",
            data={"name": "Form Upload"},
            files={"file": ("form.mp4", b"fake-content", "video/mp4")},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
```

**Verify:** `python -m pytest tests/test_videos.py::TestAsyncUpload -v`
**Commit:** `test(upload): add async upload/XHR response tests`

---

## CHECKPOINT 1 COMPLETE
**Verify:** `python -m pytest tests/ -v` — all tests pass
**Tag:** `git tag checkpoint-1`

---

# CHECKPOINT 2: Clip Creator

## Batch 4: Core Logic (parallel — 3 implementers)

All tasks in this batch have NO dependencies and run simultaneously.

### Task 4.1: Migration v4 — add clip columns
**File:** `app/database.py`
**Test:** none (covered by test suite)
**Depends:** none

Add migration v4 with `ALTER TABLE` statements to add `source_video_id`, `clip_start`, and `clip_end` columns to the `videos` table.

Also update `init_db` call signature docs to note v4 requirement.

**Edit to apply:**

After line 57 (end of MIGRATIONS dict), add:

```python
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    2: [],  # Reserved for future structural changes
    3: [TAGS_TABLE, VIDEO_TAGS_TABLE, IDX_VIDEO_TAGS_VIDEO, IDX_VIDEO_TAGS_TAG],
    4: [
        "ALTER TABLE videos ADD COLUMN source_video_id INTEGER REFERENCES videos(id)",
        "ALTER TABLE videos ADD COLUMN clip_start REAL",
        "ALTER TABLE videos ADD COLUMN clip_end REAL",
    ],
}
```

**Verify:** `python -c "from app.database import MIGRATIONS; print(len(MIGRATIONS[4]))"`
**Commit:** `feat(db): add clip columns to videos table (migration v4)`

---

### Task 4.2: Clip service — ffmpeg clip creation, validation, tag copying
**File:** `app/services/clip_service.py`
**Test:** `tests/test_clips.py` (created in task 6.1)
**Depends:** none

Design decisions:
- `create_clip(db, source_video_id, start_time, end_time)` is the single public function
- Validates: start < end, duration >= 1s, times within video duration (via ffprobe), source video exists
- Clip filename format: `clip_{source_uuid}_{start}_{end}.mp4`
- Uses `ffmpeg -ss {start} -i {input} -t {duration} -c copy {output}` for fast stream copy
- Gets source video duration via `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1`
- Copies ALL tags from source to clip via `tag_service.set_video_tags`
- Generates thumbnail for the clip via `file_service.generate_thumbnail`
- Returns the newly created video dict

```python
"""
Clip creation service: extract clips from existing videos using ffmpeg.

Relies on ffmpeg/ffprobe being available on the system PATH
(checked at app startup in main.py).
"""

import asyncio
import math
import shutil
import uuid
from pathlib import Path

from app.services import file_service, tag_service, video_service

# ── Helpers ──────────────────────────────────────────────────────

async def _get_video_duration(video_path: Path) -> float | None:
    """Return video duration in seconds via ffprobe, or None if unavailable."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None

    proc = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None

    try:
        return float(stdout.decode().strip())
    except (ValueError, TypeError):
        return None


def _validate_times(start: float, end: float, duration: float | None):
    """Validate clip time bounds. Raises ValueError with a user-facing message."""
    if start < 0:
        raise ValueError("Start time must be non-negative.")
    if end <= start:
        raise ValueError("Start must be before end.")
    if (end - start) < 1.0:
        raise ValueError("Minimum clip duration is 1 second.")
    if duration is not None and end > duration:
        raise ValueError(
            f"End time ({end:.1f}s) exceeds video duration ({duration:.1f}s)."
        )


def _generate_clip_filename(source_filename: str, start: float, end: float) -> str:
    """Generate a unique filename for the clip, e.g. clip_abc123_10_30.mp4."""
    ext = Path(source_filename).suffix
    stem = Path(source_filename).stem
    # Use a short UUID to avoid filename length issues
    short_id = uuid.uuid4().hex[:8]
    # Round times to 1 decimal for readable filenames
    start_str = f"{start:.1f}".replace(".", "_")
    end_str = f"{end:.1f}".replace(".", "_")
    return f"clip_{stem}_{start_str}_{end_str}_{short_id}{ext}"


# ── Public API ───────────────────────────────────────────────────

async def create_clip(
    db,
    source_video_id: int,
    start_time: float,
    end_time: float,
) -> dict:
    """Extract a clip from a source video and return the new video record.

    Steps:
    1. Fetch source video metadata from DB
    2. Validate time bounds (start < end, >= 1s, within duration)
    3. Generate unique clip filename
    4. Run ffmpeg to cut the clip
    5. Generate thumbnail from the clip's first frame
    6. Create new video DB record with source_video_id, clip_start, clip_end
    7. Copy source video tags to the clip
    8. Return the new video dict
    """
    # 1. Fetch source video
    source = await video_service.get_video(db, source_video_id)
    if source is None:
        raise ValueError(f"Source video with id {source_video_id} not found.")

    source_path = file_service.get_video_path(source["filename"])

    # 2. Validate times
    duration = await _get_video_duration(source_path)
    _validate_times(start_time, end_time, duration)

    # 3. Generate clip filename
    clip_duration = end_time - start_time
    clip_filename = _generate_clip_filename(source["filename"], start_time, end_time)
    clip_path = file_service.get_video_path(clip_filename)

    # 4. Run ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found. Install with: sudo apt install ffmpeg"
        )

    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-ss", f"{start_time:.3f}",
        "-i", str(source_path),
        "-t", f"{clip_duration:.3f}",
        "-c", "copy",
        str(clip_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown ffmpeg error"
        # Clean up partial output on failure
        if clip_path.exists():
            clip_path.unlink()
        raise RuntimeError(f"ffmpeg failed: {error_msg}")

    if not clip_path.exists():
        raise RuntimeError("ffmpeg completed but output file was not created.")

    # 5. Generate thumbnail
    await file_service.generate_thumbnail(clip_filename)

    # 6. Create DB record
    cursor = await db.execute(
        """INSERT INTO videos (name, filename, original_name, mime_type, file_size,
                               source_video_id, clip_start, clip_end)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"{source['name']} (clip)",
            clip_filename,
            clip_filename,
            source["mime_type"],
            clip_path.stat().st_size,
            source_video_id,
            start_time,
            end_time,
        ),
    )
    await db.commit()
    clip_id = cursor.lastrowid

    # 7. Copy source video tags
    source_tags = await tag_service.get_video_tags(db, source_video_id)
    if source_tags:
        await tag_service.set_video_tags(db, clip_id, source_tags)

    # 8. Return new video
    return await video_service.get_video(db, clip_id)
```

**Verify:** `python -c "from app.services.clip_service import create_clip; print('OK')"`
**Commit:** `feat(clip): add clip service with ffmpeg extraction`

---

### Task 4.3: Clipper JS — dual-handle seeker, click-to-seek, submit handler
**File:** `app/static/js/clipper.js`
**Test:** none (JS behavior tested via integration)
**Depends:** none

Design decisions:
- Two `<input type="range">` elements: `#clip-start` and `#clip-end`
- Handles constrained: start ≤ end, minimum 1s duration
- Clicking on the timeline (the range track) seeks the video to that point
- Display shows `{start}s / {end}s ({duration}s)`
- "Create Clip" button sends POST with start/end as JSON
- On success: redirects to `/video/{new_id}`
- On error: shows error message below button

The HTML structure expected (from clip.html):
```html
<div id="clipper">
  <video id="clip-video" ...>
  <div id="seeker">
    <input type="range" id="clip-start" min="0" max="100" step="0.1" value="0">
    <input type="range" id="clip-end" min="0" max="100" step="0.1" value="0">
  </div>
  <div id="clip-times">0s / 0s (0s)</div>
  <button id="create-clip-btn">Create Clip</button>
  <div id="clip-error"></div>
</div>
```

```javascript
/**
 * clipper.js — Dual-handle video clip seeker.
 *
 * Provides two range inputs for selecting start/end times on a video
 * timeline, with click-to-seek and constraint enforcement.
 */
(function () {
  "use strict";

  const VIDEO_ID = "clip-video";
  const START_ID = "clip-start";
  const END_ID = "clip-end";
  const TIMES_ID = "clip-times";
  const BTN_ID = "create-clip-btn";
  const ERROR_ID = "clip-error";
  const MIN_DURATION = 1; // seconds

  let video = null;
  let startInput = null;
  let endInput = null;
  let timesDisplay = null;
  let btn = null;
  let errorDisplay = null;
  let duration = 0;

  // ── Display update ────────────────────────────────────────────

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m > 0) {
      return m + "m " + (s < 10 ? "0" : "") + s.toFixed(1) + "s";
    }
    return s.toFixed(1) + "s";
  }

  function updateDisplay() {
    if (!startInput || !endInput || !timesDisplay) return;
    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);
    const dur = Math.max(0, end - start);
    timesDisplay.textContent =
      formatTime(start) + " / " + formatTime(end) + " (" + formatTime(dur) + ")";
  }

  // ── Constraint enforcement ─────────────────────────────────────

  function constrainHandles() {
    if (!startInput || !endInput) return;
    let start = parseFloat(startInput.value);
    let end = parseFloat(endInput.value);

    // Start must not exceed (end - MIN_DURATION)
    if (start > end - MIN_DURATION) {
      start = Math.max(0, end - MIN_DURATION);
    }
    // End must not be less than (start + MIN_DURATION)
    if (end < start + MIN_DURATION) {
      end = Math.min(duration, start + MIN_DURATION);
    }

    // Clamp to video duration
    start = Math.min(start, duration);
    end = Math.min(end, duration);

    startInput.value = start.toFixed(1);
    endInput.value = end.toFixed(1);

    updateDisplay();
  }

  // ── Seek video on range click ──────────────────────────────────

  function seekVideo(time) {
    if (video) {
      video.currentTime = time;
    }
  }

  function onRangeClick(event) {
    if (!video || !duration) return;
    const range = event.currentTarget;
    const rect = range.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const ratio = clickX / rect.width;
    const time = ratio * duration;
    seekVideo(time);
  }

  // ── Submit ─────────────────────────────────────────────────────

  async function onSubmit() {
    if (!btn || !startInput || !endInput || !errorDisplay) return;
    const videoId = btn.getAttribute("data-video-id");
    if (!videoId) return;

    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);

    // Client-side validation
    if (end - start < MIN_DURATION) {
      errorDisplay.textContent = "Minimum clip duration is 1 second.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Creating...";
    errorDisplay.textContent = "";

    try {
      const response = await fetch("/api/video/" + videoId + "/clip", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ start: start, end: end }),
      });

      const data = await response.json();

      if (!response.ok) {
        errorDisplay.textContent = data.error || "Failed to create clip.";
        btn.disabled = false;
        btn.textContent = "Create Clip";
        return;
      }

      // Success — redirect to new clip's detail page
      window.location.href = "/video/" + data.id;
    } catch (err) {
      errorDisplay.textContent = "Network error. Please try again.";
      btn.disabled = false;
      btn.textContent = "Create Clip";
    }
  }

  // ── Init ───────────────────────────────────────────────────────

  function init() {
    video = document.getElementById(VIDEO_ID);
    startInput = document.getElementById(START_ID);
    endInput = document.getElementById(END_ID);
    timesDisplay = document.getElementById(TIMES_ID);
    btn = document.getElementById(BTN_ID);
    errorDisplay = document.getElementById(ERROR_ID);

    if (!video || !startInput || !endInput) return;

    // Wait for video metadata to get duration
    video.addEventListener("loadedmetadata", function () {
      duration = video.duration || 0;
      if (duration > 0) {
        startInput.max = duration;
        endInput.max = duration;
        endInput.value = Math.min(30, duration).toFixed(1);
        updateDisplay();
      }
    });

    // If video is already loaded
    if (video.readyState >= 1 && video.duration) {
      duration = video.duration;
      startInput.max = duration;
      endInput.max = duration;
      endInput.value = Math.min(30, duration).toFixed(1);
      updateDisplay();
    }

    // Constraint handling
    startInput.addEventListener("input", constrainHandles);
    endInput.addEventListener("input", constrainHandles);

    // Click-to-seek
    startInput.addEventListener("click", onRangeClick);
    endInput.addEventListener("click", onRangeClick);

    // Submit button
    if (btn) {
      btn.addEventListener("click", onSubmit);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

**Verify:** `ls app/static/js/clipper.js`
**Commit:** `feat(clip): add clipper JS with dual-handle seeker`

---

### Task 4.4: Clip creator template
**File:** `app/templates/clip.html`
**Test:** none (covered by task 6.1 test_clip_page_renders)
**Depends:** none

Template extends `base.html` and renders a large video player with the dual-handle seeker.

```html
{% extends "base.html" %}
{% block title %}Clip: {{ video.name }} — Video Bank{% endblock %}

{% block content %}
<div style="max-width: 900px; margin: 0 auto;">
    <div style="margin-bottom: 1rem;">
        <a href="/video/{{ video.id }}" style="color: #4361ee; text-decoration: none; display: inline-block; margin-bottom: 0.5rem;">
            &larr; Back to video
        </a>
        <h1 style="margin-bottom: 0.25rem;">Create Clip</h1>
        <p style="color: #888; font-size: 0.9rem;">
            Source: {{ video.name }}
        </p>
    </div>

    <div id="clipper">
        <!-- Video Player -->
        <div style="background: #000; border-radius: 10px; overflow: hidden; margin-bottom: 1rem;">
            <video id="clip-video" controls style="width: 100%; display: block;" preload="metadata">
                <source src="{{ video.video_url }}" type="{{ video.mime_type }}">
                Your browser does not support the video element.
            </video>
        </div>

        <!-- Seeker Controls -->
        <div id="seeker" style="padding: 1rem; background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                <span style="font-weight: 600; font-size: 0.85rem; min-width: 3rem; color: #4361ee;">Start</span>
                <input type="range" id="clip-start" min="0" max="100" step="0.1" value="0"
                       style="flex: 1; cursor: pointer;">
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                <span style="font-weight: 600; font-size: 0.85rem; min-width: 3rem; color: #e63946;">End</span>
                <input type="range" id="clip-end" min="0" max="100" step="0.1" value="0"
                       style="flex: 1; cursor: pointer;">
            </div>

            <!-- Timestamp Display -->
            <div id="clip-times" style="text-align: center; font-size: 1.1rem; font-weight: 600; color: #333; padding: 0.5rem 0;">
                0s / 0s (0s)
            </div>

            <p style="text-align: center; font-size: 0.8rem; color: #888; margin-bottom: 0.75rem;">
                Click the timeline to seek. Minimum clip duration: 1 second.
            </p>

            <!-- Error Display -->
            <div id="clip-error" style="color: #e63946; font-size: 0.9rem; margin-bottom: 0.5rem; text-align: center;"></div>

            <!-- Create Button -->
            <div style="text-align: center;">
                <button id="create-clip-btn" class="btn btn-primary"
                        data-video-id="{{ video.id }}"
                        style="padding: 0.75rem 2rem; font-size: 1rem;">
                    Create Clip
                </button>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Verify:** Template renders at `/video/1/clip` (after routes are added)
**Commit:** `feat(clip): add clip creator template`

---

## Batch 5: Modifications (parallel — 5 implementers)

### Task 5.1: Update init_db migration version in main.py
**File:** `app/main.py`
**Test:** none (covered by existing test suite)
**Depends:** 4.1 (migration v4 must exist in database.py)

**Edit to apply:**

Old (line 67):
```python
    await init_db(migration_version=3)
```

New:
```python
    await init_db(migration_version=4)
```

Also update the ffmpeg check comment on line 72 to note clip capability:
```python
    # Check for ffmpeg (required for clip creation in Checkpoint 2)
```

**Verify:** `python -c "from app.main import app; print('OK')"`
**Commit:** `feat(clip): bump database migration to version 4`

---

### Task 5.2: Load clipper.js in base template
**File:** `app/templates/base.html`
**Test:** none (visual)
**Depends:** 4.3 (clipper.js must exist)

Add `<script src="/static/js/clipper.js"></script>` after the upload.js script.

**Edit to apply:**

Old (lines 65-67, end of file):
```html
    {% include "_upload_popup.html" %}
    <script src="/static/js/upload.js"></script>
</body>
</html>
```

New:
```html
    {% include "_upload_popup.html" %}
    <script src="/static/js/upload.js"></script>
    <script src="/static/js/clipper.js"></script>
</body>
</html>
```

**Verify:** Template renders with both script tags
**Commit:** `feat(clip): load clipper.js in base template`

---

### Task 5.3: Add clip routes to videos.py
**File:** `app/routes/videos.py`
**Test:** none (covered by task 6.1)
**Depends:** 4.2 (clip_service), 4.4 (clip.html template)

Add:
- `GET /video/{id}/clip` — renders the clip creator page
- `POST /api/video/{id}/clip` — accepts JSON `{start, end}`, calls `clip_service.create_clip()`, returns JSON `{id, redirect}`

Add import for `clip_service` and add the two new route handlers.

**Edit to apply:**

Add import after line 18:
```python
from app.services import clip_service
```

Add new routes after the `delete_video` endpoint (after line 196):

```python
@router.get("/video/{video_id}/clip")
async def clip_form(request: Request, video_id: int, db=Depends(get_db)):
    """Show the clip creator interface for a video."""
    video = await video_service.get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    thumb_stem = Path(video["filename"]).stem
    enriched["video_url"] = f"/api/video/{video_id}/file"

    return templates.TemplateResponse(
        request, "clip.html",
        {"video": enriched},
    )


@router.post("/api/video/{video_id}/clip")
async def create_clip(
    request: Request,
    video_id: int,
    db=Depends(get_db),
):
    """Create a clip from a source video. Accepts JSON body with start/end."""
    # Parse JSON body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    start = body.get("start")
    end = body.get("end")

    if start is None or end is None:
        raise HTTPException(
            status_code=400,
            detail="Both 'start' and 'end' fields are required.",
        )

    try:
        start = float(start)
        end = float(end)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="'start' and 'end' must be numeric values.",
        )

    try:
        clip = await clip_service.create_clip(db, video_id, start, end)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"id": clip["id"], "redirect": f"/video/{clip['id']}"})
```

**Verify:** `python -c "from app.routes.videos import router; print('OK')"`
**Commit:** `feat(clip): add clip creation routes`

---

### Task 5.4: Add "Clip" button to video detail page
**File:** `app/templates/video_detail.html`
**Test:** none (visual)
**Depends:** none

Add a "Clip" button next to the existing "Edit" button, so users can navigate to the clip creator.

**Edit to apply:**

Old (line 14):
```html
        <a href="/video/{{ video.id }}/edit" class="btn btn-primary btn-sm">Edit</a>
```

New:
```html
        <div style="display: flex; gap: 0.5rem;">
            <a href="/video/{{ video.id }}/clip" class="btn btn-primary btn-sm">Clip</a>
            <a href="/video/{{ video.id }}/edit" class="btn btn-primary btn-sm">Edit</a>
        </div>
```

**Verify:** Template renders with "Clip" button at `/video/1`
**Commit:** `feat(clip): add Clip button to video detail page`

---

## Batch 6: Checkpoint 2 Tests (parallel — 1 implementer)

### Task 6.1: Full clip creation test suite
**File:** `tests/test_clips.py`
**Test:** self
**Depends:** 5.3 (clip routes), 5.1 (migration v4)

Tests cover:
1. Valid clip creation (mocks ffmpeg/ffprobe)
2. Invalid times (start > end) returns 400
3. Minimum duration validation (< 1s) returns 400
4. Clip from nonexistent source returns 404
5. Clip preserves source video tags
6. Clip page renders correctly
7. Clip endpoint validates JSON body

Since ffmpeg/ffprobe may not be in the test environment, we mock `asyncio.create_subprocess_exec` for the clip service calls. The validation logic (time bounds, source exists) is tested without mocking.

```python
"""
Tests for clip creation (Checkpoint 2).

Run with: pytest tests/test_clips.py -v

These tests mock ffmpeg/ffprobe subprocess calls since those tools
may not be available in CI. The validation logic (time bounds,
source existence, tag copying) is tested directly.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


def _upload_source_video(client) -> int:
    """Helper: upload a video and return its ID."""
    import httpx
    # Use client directly since it's already an async context
    pass


class TestClipServiceValidation:
    """Tests for clip service validation rules (no ffmpeg needed)."""

    @pytest.mark.asyncio
    async def test_clip_start_after_end(self, client, db):
        """POST with start > end returns 400."""
        # Upload a source video first
        await client.post(
            "/api/videos",
            data={"name": "Source", "tags": "test-tag"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": 30, "end": 10}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Start must be before end" in data["error"]

    @pytest.mark.asyncio
    async def test_clip_minimum_duration(self, client, db):
        """POST with duration < 1s returns 400."""
        await client.post(
            "/api/videos",
            data={"name": "Source", "tags": ""},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": 5, "end": 5.5}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Minimum clip duration" in data["error"]

    @pytest.mark.asyncio
    async def test_clip_nonexistent_source(self, client, db):
        """POST for non-existent video returns 404."""
        response = await client.post(
            "/api/video/999/clip",
            content=json.dumps({"start": 0, "end": 5}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clip_missing_fields(self, client, db):
        """POST without start/end fields returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_invalid_json(self, client, db):
        """POST with non-JSON body returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_non_numeric_times(self, client, db):
        """POST with non-numeric times returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": "abc", "end": "def"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestClipPage:
    """Tests for the clip creator page."""

    @pytest.mark.asyncio
    async def test_clip_page_renders(self, client, db):
        """GET /video/{id}/clip shows the clip creator."""
        await client.post(
            "/api/videos",
            data={"name": "Clip Source", "tags": ""},
            files={"file": ("src.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1/clip")
        assert response.status_code == 200
        assert "Create Clip" in response.text
        assert "clip-video" in response.text  # video element ID
        assert "clip-start" in response.text  # start range ID
        assert "clip-end" in response.text    # end range ID
        assert "create-clip-btn" in response.text  # button ID

    @pytest.mark.asyncio
    async def test_clip_page_not_found(self, client, db):
        """GET /video/{id}/clip for missing id returns 404."""
        response = await client.get("/video/999/clip")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clip_page_shows_source_name(self, client, db):
        """Clip page shows the source video name."""
        await client.post(
            "/api/videos",
            data={"name": "My Awesome Video", "tags": ""},
            files={"file": ("src.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1/clip")
        assert "My Awesome Video" in response.text


@pytest.mark.usefixtures("db")
class TestClipCreationWithMock:
    """Tests that mock ffmpeg/ffprobe for end-to-end clip creation."""

    @pytest.mark.asyncio
    async def test_clip_creates_db_record(self, client, db):
        """Successful clip creation inserts a DB record with source_video_id."""
        await client.post(
            "/api/videos",
            data={"name": "Source Vid", "tags": "alpha, beta"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        # Mock ffprobe to return a 60s duration
        # Mock ffmpeg to succeed (return code 0, create a dummy file)
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
                return_value=(b"60.0\n", b"")
            )

            # Mock ffmpeg subprocess
            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 0
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b""))

            # Return ffprobe on first call, ffmpeg on second
            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            # Also need to mock file existence for the clip output path
            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": type("Stat", (), {"st_size": 1024})()})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": type("Stat", (), {"st_size": 1024})(),
                    "unlink": lambda self: None,
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 10, "end": 20}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] == 2  # Second video (the clip)

        # Verify clip record in DB
        cursor = await db.execute("SELECT * FROM videos WHERE id = 2")
        clip = dict(await cursor.fetchone())
        assert clip["source_video_id"] == 1
        assert clip["clip_start"] == 10.0
        assert clip["clip_end"] == 20.0
        assert clip["name"] == "Source Vid (clip)"

    @pytest.mark.asyncio
    async def test_clip_copies_source_tags(self, client, db):
        """Clip creation copies all tags from source video."""
        await client.post(
            "/api/videos",
            data={"name": "Tagged Source", "tags": "tutorial, funny, demo"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe_proc = AsyncMock()
            mock_ffprobe_proc.returncode = 0
            mock_ffprobe_proc.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 0
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b""))

            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": type("Stat", (), {"st_size": 1024})()})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": type("Stat", (), {"st_size": 1024})(),
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 5, "end": 15}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 200

        # Verify clip has the same tags
        detail = await client.get("/video/2")
        assert "tutorial" in detail.text
        assert "funny" in detail.text
        assert "demo" in detail.text

    @pytest.mark.asyncio
    async def test_clip_ffmpeg_failure_returns_500(self, client, db):
        """When ffmpeg fails, clip endpoint returns 500."""
        await client.post(
            "/api/videos",
            data={"name": "Failing Source", "tags": ""},
            files={"file": ("fail.mp4", b"fake-video-content", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe_proc = AsyncMock()
            mock_ffprobe_proc.returncode = 0
            mock_ffprobe_proc.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 1
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error output"))

            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": type("Stat", (), {"st_size": 1024})()})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: False,
                    "unlink": lambda self: None,
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 0, "end": 10}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "ffmpeg" in data["error"].lower()
```

**Verify:** `python -m pytest tests/test_clips.py -v`
**Commit:** `test(clip): add full clip creation test suite`

---

## RUNNING ALL TESTS AFTER CHECKPOINT 2

```
$ python -m pytest tests/ -v

Expected output (all passing):
- test_videos.py ....... (existing + new XHR tests)
- test_tags.py ........ (existing)
- test_clips.py ....... (new clip tests)
```

---

## File Summary

| # | Action | File | Batch |
|---|--------|------|-------|
| 1.1 | Create | `app/static/__init__.py` | 1 |
| 1.2 | Create | `app/static/js/upload.js` | 1 |
| 1.3 | Create | `app/templates/_upload_popup.html` | 1 |
| 2.1 | Modify | `app/main.py` (mount /static) | 2 |
| 2.2 | Modify | `app/templates/base.html` (popup + upload.js) | 2 |
| 2.3 | Modify | `app/routes/videos.py` (XHR JSON response) | 2 |
| 2.4 | Modify | `app/templates/upload.html` (form id) | 2 |
| 3.1 | Modify | `tests/test_videos.py` (XHR tests) | 3 |
| 4.1 | Modify | `app/database.py` (migration v4) | 4 |
| 4.2 | Create | `app/services/clip_service.py` | 4 |
| 4.3 | Create | `app/static/js/clipper.js` | 4 |
| 4.4 | Create | `app/templates/clip.html` | 4 |
| 5.1 | Modify | `app/main.py` (migration v4 init) | 5 |
| 5.2 | Modify | `app/templates/base.html` (clipper.js) | 5 |
| 5.3 | Modify | `app/routes/videos.py` (clip routes) | 5 |
| 5.4 | Modify | `app/templates/video_detail.html` (Clip button) | 5 |
| 6.1 | Create | `tests/test_clips.py` | 6 |

**Total: 17 tasks across 6 parallel batches**
- Checkpoint 1: 8 tasks (3 batches)
- Checkpoint 2: 9 tasks (3 batches)
