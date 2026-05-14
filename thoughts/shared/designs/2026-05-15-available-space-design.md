---
date: 2026-05-15
topic: "Available Disk Space Indicator & Upload Guard"
status: validated
---

## Problem Statement

Users need visibility into remaining server disk space, and the app should prevent uploads that would fill the disk past 95% capacity. Without this, users can unknowingly fill the disk, causing failures for all subsequent uploads and potentially affecting server stability.

## Constraints

- Zero new Python dependencies — no psutil, no third-party monitoring libs
- Must follow existing patterns: HTMX for dynamic UI, server-rendered fragments, `#main-content` swaps
- Must be easy to self-host on Ubuntu (the deployment target is `/opt/video-bank/`)
- The disk check path must be the same directory as uploads (`uploads/videos/`)
- All 45 existing tests must remain passing
- New code must be testable with standard pytest patterns (mocks for `shutil.disk_usage`)

## Approach

Two-pronged design:

1. **Display**: An HTMX-loaded space indicator badge in the nav bar, showing available space with color coding (green/yellow/red). Loaded via a lightweight fragment endpoint on every page load — zero changes to existing route handlers.

2. **Guard**: A disk-space check added to the existing `file_service.validate_file()` function, rejecting uploads that would push disk usage past 95%. Uses the same `ValueError` path that existing validation uses — no new error handling infrastructure.

I considered a middleware-based template context injection but rejected it because:
- It couples every page render to disk I/O
- It requires more complex app setup changes
- The HTMX fragment approach is more consistent with the existing architecture patterns

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Nav Bar (base.html)                 │
│  [Video Bank]  [Upload]  │  ◄── hx-get="/api/space"  │
│                          │  hx-trigger="load"         │
└──────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  GET /api/space          │
              │  → file_service          │
              │    .get_available_space() │
              │  → _space_fragment.html  │
              └─────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  "12.3 GB free" (green)  │
              │  or "2.1 GB free" (red)  │
              └─────────────────────────┘

Upload flow:
  POST /api/videos
    → file_service.validate_file()
        → check extension ✓
        → check file size ✓
        → check disk space: (used + file_size) / total ≤ 0.95
    → file_service.save_upload()
```

## Components

### `app/services/file_service.py` — Disk space utilities

One new function and one addition to an existing function:

- **`get_available_space(directory: Path | None = None) -> dict`**: Wraps `shutil.disk_usage()` on the upload videos directory. Returns `{total, used, free, percent_used, free_gb}` (free_gb is human-readable, rounded to 1 decimal). Gracefully handles `OSError` by returning a sentinel dict with `error: True`.

- **`validate_file()` extended**: After existing extension and size checks, calls `get_available_space()`. If `(used + file_size) / total > 0.95`, returns `"Not enough disk space (would exceed 95% capacity)."`

### `app/routes/videos.py` — New space endpoint

- **`GET /api/space`**: Calls `get_available_space()`, renders `_space_fragment.html` with the result. Returns HTML fragment (not JSON) for HTMX swap. No auth — this is a self-hosted internal tool.

### `app/templates/_space_fragment.html` — Space indicator template

Small partial template (~8 lines):
- Shows "X.X GB free" text
- Applies CSS class based on thresholds:
  - `space-ok` (green): > 20% free
  - `space-warn` (yellow): 10–20% free
  - `space-critical` (red): < 10% free (or on error)
- If space info unavailable (error), shows "Space: unknown" with gray styling

### `app/templates/base.html` — Nav bar integration

- Add `<span id="space-indicator" hx-get="/api/space" hx-trigger="load"></span>` in the nav bar, after the links
- Add CSS rules for `.space-ok`, `.space-warn`, `.space-critical` classes (inline style block, following existing CSS convention)

## Data Flow

**Page load (display):**
1. User navigates to any page → `base.html` renders
2. HTMX sees `hx-get="/api/space"` on `#space-indicator`
3. Browser fires `GET /api/space` in background
4. Route handler calls `file_service.get_available_space(VIDEOS_DIR)`
5. `shutil.disk_usage()` returns `(total, used, free)` tuple
6. Route calculates `percent_used = used / total`, `free_gb = free / (1024^3)`
7. Renders `_space_fragment.html` with this data
8. HTMX swaps result into `#space-indicator` — badge appears in nav

**Upload (guard):**
1. User submits upload form → `POST /api/videos`
2. Route reads file content into memory (existing behavior)
3. Calls `video_service.create_video()` → which calls `file_service.validate_file()`
4. Disk space check: `projected = (used + file_size) / total`
5. If `projected > 0.95` → `raise ValueError("Not enough disk space...")`
6. Caught by route handler → JSON error response (XHR) or re-rendered form (non-XHR)
7. If under threshold → proceeds to save + thumbnail + DB insert (existing flow)

## Error Handling

| Scenario | Display Behavior | Upload Behavior |
|----------|-----------------|-----------------|
| `shutil.disk_usage()` raises `OSError` | Fragment shows "Space: unknown" (gray, no panic) | Upload proceeds (don't block on unavailable data) |
| Disk > 95% full | Fragment shows red warning with "X.X GB free" | Upload rejected with clear error message |
| Upload exactly at 95% | Warning | Allowed (≤ 95%, not > 95%) |
| Upload pushes past 95% | Warning | Rejected |

## Testing Strategy

### New tests in `test_videos.py`:

1. **`test_available_space`** — Mock `shutil.disk_usage` to return known values, call `get_available_space()`, verify `free_gb` and `percent_used` are computed correctly.

2. **`test_upload_rejected_disk_full`** — Mock `shutil.disk_usage` to return near-full disk (95.1% used). Upload a small file. Expect 400 response with disk-full error message.

3. **`test_upload_allowed_disk_available`** — Mock `shutil.disk_usage` to return plenty of space (50% used). Upload a file. Expect 303/JSON success.

4. **`test_space_api_endpoint`** — `GET /api/space` returns 200 with HTML containing expected text like "GB free" and appropriate CSS class.

5. **`test_disk_usage_error_handling`** — Mock `shutil.disk_usage` to raise `OSError`. Verify `get_available_space()` returns error sentinel. Verify uploads still work (not blocked by failing space check).

### Mocking strategy:
```python
with patch("app.services.file_service.shutil.disk_usage") as mock_du:
    mock_du.return_value = (1_000_000_000_000, 500_000_000_000, 500_000_000_000)
    # 500GB used out of 1TB → 50%
    # test assertions...
```

This follows the same `unittest.mock.patch` pattern already used in `test_clips.py` for mocking ffmpeg/ffprobe.

## Open Questions

- Should the indicator auto-refresh periodically? Could add `hx-trigger="load, every 120s"` easily — not needed for v1 but trivial to add later.
- Should we check disk before reading the file into memory? Ideally yes, but that would require restructuring the upload route (currently reads file, then validates). That's a separate concern — the disk check at validation time still prevents the save.
