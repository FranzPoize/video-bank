---
date: 2026-05-15
topic: "App Logging — File-based logging with rotation"
status: validated
---

## Problem Statement

The app has no persistent logging. Under systemd, uvicorn's stdout goes to journald, but there are no file-based logs. The single `print()` call for the ffmpeg warning is the only instrumentation. When something goes wrong in production (ffmpeg crash, disk full, upload failure), there's no trail to debug.

## Constraints

- Zero new Python dependencies — `logging` is stdlib
- Must work with the existing systemd service at `/opt/video-bank/`
- Must not require app restarts for log rotation
- Must follow standard Ubuntu patterns (logrotate)
- Must handle the `www-data` user permissions correctly
- All 52 existing tests must remain passing

## Approach

Three-layer logging stack:
1. **Python `logging` module** configured at app startup — writes to a file, structured format, levels for different event types
2. **systemd integration** — `ExecStartPre` creates the logs directory with proper ownership, environment variable for path
3. **logrotate** — daily rotation, 30-day retention, `copytruncate` so the app doesn't need to reopen file handles

No new dependencies. No changes to the logging framework (no loguru, no structlog).

## Architecture

```
App startup (main.py)
  → logging.basicConfig(...)
  → FileHandler at /opt/video-bank/logs/video-bank.log
  → Root logger captures app, uvicorn, and library logs

systemd
  → video-bank.service:
      ExecStartPre=mkdir -p /opt/video-bank/logs
      ExecStartPre=chown www-data:www-data /opt/video-bank/logs
  → Logs directory created with proper ownership before app starts

logrotate (/etc/logrotate.d/video-bank)
  → /opt/video-bank/logs/*.log {
        daily
        rotate 30
        compress
        copytruncate
        ...
    }
  → copytruncate: app never needs to reopen or rotate — the file is
    truncated in-place after copying
```

## Components

### `app/main.py` — Logging configuration

Added during the lifespan startup handler:

```python
import logging

LOG_DIR = os.environ.get("LOG_DIR", str(_project_root / "logs"))
LOG_FILE = os.path.join(LOG_DIR, "video-bank.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    filename=LOG_FILE,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    # Don't propagate to stderr (avoid duplication with uvicorn's own logs)
    force=True,
)
```

The `force=True` parameter (Python 3.8+) ensures the config replaces any pre-existing logger setup (uvicorn configures its own loggers on import).

### Logged events

Existing `print()` calls are replaced with the appropriate logging level. New log calls are added at key points:

| Location | Event | Level |
|----------|-------|-------|
| `main.py` — startup | App started, DB path, ffmpeg presence | INFO |
| `main.py` — startup | ffmpeg not found (existing print) | WARNING |
| `file_service.py` — validate_file | Disk near capacity | WARNING |
| `file_service.py` — save_upload | File saved with size | INFO |
| `file_service.py` — generate_thumbnail | ffmpeg failure | ERROR |
| `file_service.py` — generate_thumbnail | Thumbnail generated | INFO |
| `file_service.py` — get_available_space | disk_usage() OSError | WARNING |
| `video_service.py` — create_video | Upload rejected (validation) | WARNING |
| `video_service.py` — delete_video | Video deleted | INFO |
| `clip_service.py` — create_clip | Clip created with times | INFO |
| `clip_service.py` — create_clip | ffmpeg failure | ERROR |

This is a representative set — not all may be implemented in the initial pass. Priority is: startup, upload, clip creation, and errors.

### `video-bank.service` — Log directory setup

Two `ExecStartPre` lines added before the main `ExecStart`:

```ini
ExecStartPre=mkdir -p /opt/video-bank/logs
ExecStartPre=chown www-data:www-data /opt/video-bank/logs
```

And the `LOG_DIR` environment variable:

```ini
Environment="LOG_DIR=/opt/video-bank/logs"
```

### `/etc/logrotate.d/video-bank`

Standard logrotate config:

```
/opt/video-bank/logs/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    copytruncate
    dateext
}
```

Key choices:
- `copytruncate`: App keeps writing to the same file handle; logrotate copies then truncates. No `SIGHUP` handling needed.
- `daily` + `rotate 30`: One month of daily logs.
- `dateext`: Logs get `.YYYY-MM-DD` suffixes for easy browsing.
- `missingok` + `notifempty`: No errors if no logs yet, no rotation for empty files.

## Data Flow

```
App starts
  → logging.basicConfig() opens video-bank.log for append
  → All log calls write to this file
  → systemd journal still captures stdout/stderr (dual capture)

Midnight
  → logrotate runs (cron.daily)
  → Copies video-bank.log → video-bank.log.2026-05-16
  → Truncates video-bank.log to 0 bytes
  → App continues writing — new data goes to empty file (same inode)
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Log directory doesn't exist | `FileHandler` raises — but the handler fallback is stderr, so logs go to journald |
| Log file unwritable | Same — stderr fallback, systemd captures it |
| logrotate fails (disk full) | App keeps writing to existing file, no crash |
| `LOG_DIR` env var unset | Defaults to `{project_root}/logs` (development-friendly) |

The logging setup uses `logging.basicConfig` which has no error at import time — it's called at startup. If it fails, the app still starts (logs go to stderr). This is fails-open.

## Testing Strategy

Logging is infrastructure — the core testing focus is that the app still works:

1. **No regression**: `pytest -q` — all 52 existing tests pass
2. **Log output verification** (optional): Add a few tests that verify `caplog` (pytest's log capture fixture) contains expected messages for key events like:
   - Upload creates a log at INFO level
   - ffmpeg failure creates a log at ERROR level
   - Valid file passes without WARNING/ERROR
3. **Don't test log files directly**: In tests, use pytest's `caplog` fixture which captures log records in memory. No file I/O in tests.

## Open Questions

- Should uvicorn's own request logs also go to the file? Currently they go to stderr → journald. We could capture them via `logging.config.dictConfig` and a logger hierarchy, but that's more complex. For v1, app logs to file, request logs to journald.
- `force=True` in `basicConfig` — requires Python 3.8+. The server runs Python 3.14, so this is fine, but worth noting if deploying on older systems.
