---
date: 2026-05-14
topic: "Clip Creator — Async Upload + Video Clipping"
status: draft
---

## Problem Statement

Add two features to the video bank:

1. **Async upload with progress** — large file uploads run in the background with a visible progress indicator at the bottom-left of the screen, persisting across page navigations
2. **Video clip creator** — select a start/end time on any video to cut out a clip, which becomes a new video entry in the bank

## Constraints

- **Must be easy to self-host on Ubuntu** — no new runtime dependencies (ffmpeg already required)
- **Code must be simple** — no inversion of control, no heavy JS frameworks
- **Code must be testable** — unit tests for clip service, integration tests for routes
- **Incremental delivery** — two working checkpoints, each independently testable
- **Async upload must survive page navigation** — in-flight uploads continue when user browses away

## Approach

**Two checkpoints, zero new dependencies.**

- **Upload progress:** Vanilla JS + XMLHttpRequest (native `progress` events). sessionStorage stores active upload state across navigations. No new libraries needed.
- **Clip seeker:** Vanilla JS + HTML5 `<video>` API with `<input type="range">` dual handles. No video player library needed.
- **Clip generation:** ffmpeg subprocess (already in the project) with `-c copy` for lossless stream copy.
- **New static directory:** `/static` mounted in FastAPI for JS files (the project currently has no static JS).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Browser                        │
│  ┌───────────────────┐  ┌────────────────────┐   │
│  │ upload.js          │  │ clipper.js         │   │
│  │ XHR + progress     │  │ dual-handle seeker │   │
│  │ popup (bottom-left)│  │ click-to-seek      │   │
│  └────────┬──────────┘  └─────────┬──────────┘   │
│           │                       │              │
│           │ POST /api/videos      │ POST          │
│           │ (XHR, not form)       │ /api/video/X/ │
│           │                       │ clip          │
└───────────┼───────────────────────┼──────────────┘
            │                       │
┌───────────▼───────────────────────▼──────────────┐
│              FastAPI Server                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │Upload    │  │ Clip     │  │ Existing      │   │
│  │Routes    │  │ Routes   │  │ Routes        │   │
│  └────┬─────┘  └────┬─────┘  └──────┬────────┘   │
│       │              │               │            │
│  ┌────▼──────────────▼───────────────▼─────────┐  │
│  │         Service Layer                       │  │
│  │  video_service, tag_service, clip_service   │  │
│  └────┬──────────────────────────────────┬─────┘  │
│       │                                  │        │
│  ┌────▼─────┐                    ┌───────▼──────┐ │
│  │ SQLite   │                    │  Filesystem  │ │
│  │ (aiosqlite)                   │  uploads/    │ │
│  └──────────┘                    └──────────────┘ │
└──────────────────────────────────────────────────┘
```

## Components

### New: `static/js/upload.js`
- Intercepts the upload form submission
- Creates an XMLHttpRequest with `upload.onprogress` event
- Manages a popup `<div id="upload-popup">` appended to `document.body`
- Stores active uploads in sessionStorage so popup state survives navigation
- On page load, checks sessionStorage for in-flight uploads and restores popup
- Popup shows: filename, progress bar (percentage), status (uploading/completed/failed)

### New: `static/js/clipper.js`
- Initializes two `<input type="range">` handles on the video timeline
- Left handle = clip start, right handle = clip end
- Clicking on the timeline seeks the video to the clicked time
- Handles are constrained: start ≤ end, minimum clip duration 1 second
- Updates a display showing selected duration `${duration}s`
- "Create Clip" button sends POST with `start` and `end` params

### New: `app/services/clip_service.py`
- `create_clip(db, source_video_id, start_time, end_time)`:
  1. Reads source video metadata from DB
  2. Validates start < end and within video duration
  3. Generates a unique filename for the clip
  4. Runs: `ffmpeg -ss {start} -i {input} -t {duration} -c copy {output}`
  5. Generates thumbnail from first frame of clip
  6. Creates new video DB record with `source_video_id`, `clip_start`, `clip_end`
  7. Tags: copies source video tags to the new clip
  8. Returns the new video record

### Modified: `app/database.py`
- Migration v4: Add columns to `videos` table:
  - `source_video_id INTEGER REFERENCES videos(id)` (nullable — null for original uploads)
  - `clip_start REAL` (nullable — start time in seconds)
  - `clip_end REAL` (nullable — end time in seconds)

### Modified: `app/routes/videos.py`
- `POST /api/videos` — enhance to return JSON for XHR uploads (already does JSON redirect, but needs to return structured JSON response for the JS handler)
- New: `GET /video/{id}/clip` — renders the clip creator interface
- New: `POST /api/video/{id}/clip` — accepts `start` and `end` form params, calls `clip_service.create_clip()`, returns JSON with new video ID

### Modified: `app/templates/base.html`
- Add empty `<div id="upload-popup" style="position: fixed; bottom: 1rem; left: 1rem; ...">` container
- Add `<script src="/static/js/upload.js">` and `<script src="/static/js/clipper.js">`

### New: `app/templates/clip.html`
- Extends `base.html`
- Large video player
- Dual-handle seeker bar below the video
- Timestamp display: `{start}s / {end}s ({duration}s)`
- "Create Clip" button
- Shows clip preview text area

### New: `app/static/` directory
- FastAPI mounts `StaticFiles` at `/static`
- Contains `js/upload.js` and `js/clipper.js`

## Data Flow

### Async Upload Flow
```
User selects file + fills name/tags → clicks Upload
  → upload.js intercepts form submit
  → Creates XHR to POST /api/videos (FormData)
  → XHR.upload.onprogress → updates progress bar in popup
  → On success:
      → Popup shows "Completed!"
      → Clears from sessionStorage
      → Redirect via window.location or HTMX trigger
  → On error:
      → Popup shows "Failed"
  → If user navigates away:
      → XHR continues running (in background tab)
      → sessionStorage still has the upload record
      → On return, upload.js checks sessionStorage, restores popup
```

### Clip Creation Flow
```
User opens /video/{id}/clip
  → Template renders video player + dual-handle seeker
  → clipper.js initializes handles, sets video.currentTime on click
  → User sets start/end, clicks "Create Clip"
  → POST /api/video/{id}/clip with {start, end}
  → clip_service.create_clip():
      1. Validates times
      2. Generates clip filename: clip_{source_uuid}_{start}_{end}.mp4
      3. Runs ffmpeg -ss START -i INPUT -t DURATION -c copy OUTPUT
      4. Generates thumbnail
      5. Creates DB record with source_video_id, clip_start, clip_end
      6. Copies source video tags
  → Returns JSON with new video ID
  → JS redirects to /video/{new_id}
```

## Error Handling

- **Upload error during XHR:** Popup shows "Upload failed" with retry button. File is not committed to DB
- **ffmpeg fails during clip:** Return 500 with error message. Validate ffmpeg exists before running
- **Invalid clip times:** Return 400 with "Start must be before end" or "Minimum clip duration is 1 second"
- **Clip start/end exceeds video duration:** Need to get video duration first (via ffprobe or ffmpeg probe). Return 400 if out of bounds
- **Large files:** XHR has no built-in limit, but server-side limit handles this (existing `MAX_UPLOAD_SIZE` env var)
- **sessionStorage full:** Upload still works, popup just won't persist across navigations (degraded gracefully)

## Testing Strategy

- **`tests/test_clips.py`** — New test file for clip creation:
  - Test clip creation with valid times
  - Test clip creation with invalid times (start > end)
  - Test clip duration validation (< 1 second)
  - Test clip from nonexistent source video
  - Test clip preserves source video tags
  - Test clip page renders
- **`tests/test_upload.js`** — Not applicable (JS behavior). We test the upload endpoint still works at the HTTP level (already covered in `test_videos.py`)

## Open Questions

- **Getting video duration for validation:** Need either ffprobe (part of ffmpeg) or a Python mediainfo library. ffprobe is the lightest option — it comes with ffmpeg. **Default: use ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1**
- **Upload progress popup UX:** Showing uploads across navigation. sessionStorage handles this, but active progress bars reset (XHR can't be serialized). The popup will show "Uploading..." without a live bar after navigation — the completion toast appears when the user returns. **Acceptable trade-off.**
- **Clip codec handling:** `-c copy` is fast but requires the clip to start on a keyframe. For precise cuts, re-encoding (`-c libx264`) would be needed but is slower. **Default: use -c copy for speed. Discuss at implementation.**
- **Should clips inherit ALL tags from source or none?** **Default: copy source tags.**
- **Backend upload endpoint change:** Currently `/api/videos` returns a redirect for form uploads. We need it to work with XHR too. **Solution: if request has `HX-Request` header or `X-Requested-With: XMLHttpRequest`, return JSON instead of redirect.**

## Incremental Plan (2 Checkpoints)

### Checkpoint 1: Async Upload + Progress Popup
- Create `static/` directory, mount in FastAPI
- Create `upload.js` with XHR upload, progress events, sessionStorage persistence
- Add upload popup HTML to `base.html`
- Update `/api/videos` POST handler to detect XHR and return JSON
- Dropzone-style UI: upload form submits async, popup shows in bottom-left
- Tests: verify upload endpoint returns JSON for XHR requests
- **CHECKPOINT HERE!**

### Checkpoint 2: Clip Creator
- Migration v4: add `source_video_id`, `clip_start`, `clip_end` to videos table
- Create `clip_service.py` with `create_clip()` function
- Create `clipper.js` with dual-handle seeker
- Create `clip.html` template
- Add clip routes to `videos.py`
- Add "Clip" button to `video_detail.html`
- Tests: full clip creation and validation test suite
- **CHECKPOINT HERE!**
