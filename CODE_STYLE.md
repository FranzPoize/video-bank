# Video Bank — Code Style Guide

> Observed conventions from the codebase. Follow these when adding or modifying code.

---

## Naming Conventions

| Category | Convention | Examples |
|----------|-----------|----------|
| Python files | `snake_case.py` | `video_service.py`, `test_videos.py` |
| JS files | `snake_case.js` | `upload.js`, `clipper.js` |
| HTML templates | `snake_case.html` | `video_detail.html` |
| Template fragments | `_snake_case.html` | `_content.html`, `_space_fragment.html` |
| Python classes | `PascalCase` | `TestVideoUpload`, `TestTagCreation` |
| Public functions | `snake_case` | `create_video()`, `list_all_tags()` |
| Private functions | `_snake_case` | `_video_to_card()`, `_validate_times()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_UPLOAD_SIZE`, `DEFAULT_DB_PATH` |
| Module globals | `_snake_case` | `_project_root`, `_cached_translations` |
| Local variables | `snake_case` | `clip_duration`, `thumb_stem` |
| Translation keys | `dotted.namespace.key` | `btn.save_changes`, `error.video_not_found` |
| DB columns | `snake_case` | `source_video_id`, `clip_start` |
| DB indexes | `idx_{table}_{column}` | `idx_video_tags_video_id` |
| CSS classes | `kebab-case` / `prefix-*` | `space-critical`, `btn-primary`, `seeker-slider` |
| JS functions | `camelCase` | `handleUpload()`, `restoreState()` |
| JS variables | `camelCase` | `formData`, `popup` |
| JS constants | `UPPER_SNAKE_CASE` | `STORAGE_KEY`, `POPUP_ID` |
| Test methods | `test_action_scenario` | `test_upload_unsupported_format` |
| URL path params | `{snake_case}` | `{video_id}`, `{tag_id}` |

---

## File Organization

### Python files — one module per file, structured as:
```
"""
Docstring: purpose of this module — one line, then blank line, then detail.

Only present in files with > 5 lines of code.
"""
imports...     # stdlib first, third-party second, local third (alphabetical groups)

constants...   # UPPER_SNAKE_CASE

logger = logging.getLogger(__name__)   # module-level logger

private helpers...   # _prefixed functions

public API...        # non-prefixed functions
```

### Template files:
- **`base.html`** — layout (nav, style, footer). Does NOT extend anything.
- **Page templates** (`index.html`, `upload.html`, etc.) — extend `base.html`.
- **Fragment templates** (`_content.html`, `_space_fragment.html`) — HTML partials, no `{% extends %}`.
- Template blocks used: `{% block title %}`, `{% block content %}`, `{% block extra_head %}`.

### JS files:
- Wrapped in IIFE: `(function () { "use strict"; ... })();`
- DOM ready check: `document.readyState === "loading"` pattern.
- Translation helper `_(key)` at top, constants second, functions below.

---

## Import Style

```python
# Group 1: Python stdlib (alphabetical)
import logging
import os
from pathlib import Path

# Group 2: Third-party (alphabetical)
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

# Group 3: Local application (alphabetical by full path)
from app.database import get_db
from app.services import tag_service, video_service
from app.templates import templates
```

- One import per line for stdlib; `from` imports grouped by module.
- No `*` imports. Ever.
- Relative imports avoided (use full `app.xxx` path).

---

## Code Patterns

### Async Discipline
```python
# I/O operations: always async
async def save_upload(file_content: bytes, original_name: str) -> str:
    ...

# Pure computation: always sync
def _validate_times(start: float, end: float, duration: float | None):
    ...
```

### FastAPI Route Pattern
```python
@router.get("/video/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db)):
    """Docstring: what this endpoint does."""
    i18n = _get_i18n(request)                          # 1. Get i18n context
    video = await video_service.get_video_with_tags(...) # 2. Call service
    if video is None:
        raise HTTPException(status_code=404, ...)       # 3. Handle not-found
    return templates.TemplateResponse(                   # 4. Return template
        request, "video_detail.html", {**i18n, "video": enriched},
    )
```

### Service Function Pattern
```python
async def get_video(db, video_id: int) -> dict | None:
    """Docstring: what it does and returns."""
    cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)     # Convert aiosqlite.Row to plain dict
```

### Error Handling

**Business logic** — return `str | None` or raise `ValueError`:
```python
def validate_file(filename: str, file_size: int) -> str | None:
    """Return error message or None."""
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported format '.{ext}'."
    ...

# Or raise for unrecoverable errors:
if not tag_name:
    raise ValueError("Tag name cannot be empty")
```

**Route handlers** — catch `ValueError` from services, return user-facing messages:
```python
try:
    video = await video_service.create_video(...)
except ValueError as e:
    return JSONResponse({"error": str(e)}, status_code=400)
```

**Not-found cases** — use `HTTPException(status_code=404)`:
```python
video = await video_service.get_video(db, video_id)
if video is None:
    raise HTTPException(status_code=404, detail="Video not found")
```

**Infrastructure errors** — raise `RuntimeError` (ffmpeg failures, disk issues):
```python
raise RuntimeError(f"ffmpeg failed: {error_msg}")
```

### DB Connection Management
```python
# Production: FastAPI dependency injection
async def get_db(db_path: str | None = None):
    path = db_path or DEFAULT_DB_PATH
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

# Override for tests:
_app.dependency_overrides[get_db] = lambda: db
```

### Logger Pattern
```python
logger = logging.getLogger(__name__)     # module-level

# Logging levels used:
logger.info("File saved: %s (%d bytes)", stored_name, len(file_content))
logger.warning("Upload rejected (%s): %s", original_name, error)
logger.error("ffmpeg failed for clip from video %d: %s", video_id, error_msg)
```

- Use `%s`-style formatting (not f-strings) so lazy evaluation works.
- Include identifying IDs and filenames in every log message.
- Test environment skips file logging (check: `"PYTEST_CURRENT_TEST" not in os.environ`).

### i18n Pattern
```python
# Python routes:
i18n = _get_i18n(request)       # from request.state (set by middleware)
_ = i18n["_"]                    # translation function
detail = _("error.page_not_found")

# Jinja2 templates:
{{ _("nav.video_bank") }}
{{ _("btn.save_changes") }}

# JavaScript:
function _(key) {
    return (window.TRANSLATIONS && window.TRANSLATIONS[key]) || key;
}
// Keys injected in base.html: <script> window.TRANSLATIONS = { ... }; </script>
```

Translation keys use dotted namespace: `{category}.{key}` or `{category}.{subcategory}.{key}`.
English is the base file; target languages override. Missing keys fall back to the key itself.

---

## Testing Patterns

### Fixtures (`tests/conftest.py`)
```python
@pytest_asyncio.fixture
async def db():
    """In-memory SQLite for each test."""
    db_conn = await aiosqlite.connect(":memory:")
    await db_conn.execute("PRAGMA foreign_keys = ON")
    db_conn.row_factory = aiosqlite.Row
    # Apply schema
    for version in range(1, 5):
        for stmt in MIGRATIONS.get(version, []):
            await db_conn.execute(stmt)
    await db_conn.commit()
    yield db_conn
    await db_conn.close()

@pytest_asyncio.fixture
async def client(db):
    """httpx test client with DB override."""
    _app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    _app.dependency_overrides.clear()
```

### Test Class Structure
```python
class TestVideoUpload:
    """Tests for the upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_success(self, client):
        """POST /api/videos with valid data redirects to list."""
        response = await client.post(
            "/api/videos",
            data={"name": "My Clip"},
            files={"file": ("clip.mp4", b"fake-video-content", "video/mp4")},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
```

- Test classes: `PascalCase` with `Test` prefix.
- Test methods: `snake_case` with `test_` prefix, descriptive of scenario.
- All async tests need `@pytest.mark.asyncio`.
- Docstrings on each test method describing the scenario.
- Mock external dependencies (`shutil.disk_usage`, ffmpeg) with `unittest.mock.patch`.
- Use `DiskUsage = collections.namedtuple("DiskUsage", ["total", "used", "free"])` for mock shape.

### Mock Pattern
```python
def test_something(self, client):
    with patch("app.services.file_service.shutil.disk_usage") as mock_du:
        mock_du.return_value = DiskUsage(1_000_000_000_000, 500_000_000_000, 500_000_000_000)
        response = await client.get("/api/space")
    assert response.status_code == 200
```

---

## Database Patterns

```sql
-- CREATE TABLE IF NOT EXISTS (idempotent)
-- INTEGER PRIMARY KEY AUTOINCREMENT for IDs
-- Foreign keys with ON DELETE CASCADE
-- UNIQUE constraints for join tables
-- Names are lowercased/normalized in application layer

-- ALTER TABLE ADD COLUMN for migrations
-- Duplicate column errors silently ignored (idempotent)
```

- All queries parameterized with `?` placeholders.
- Always call `await db.commit()` after writes.
- Convert `aiosqlite.Row` to `dict(row)` for return values.
- Enable foreign keys: `PRAGMA foreign_keys = ON` on every connection.

---

## Do's and Don'ts

### Do
- ✅ Write docstrings for every module, public function, and route handler.
- ✅ Use type hints for all function parameters and return values.
- ✅ Return `dict | None` from service functions (dict for found, None for not-found).
- ✅ Convert `aosqlite.Row` to `dict(row)` before returning from service layer.
- ✅ Use `{**i18n, ...}` to spread translation context in template responses.
- ✅ Use `%s` formatting in log messages (not f-strings).
- ✅ Name template fragments with `_` prefix.
- ✅ Guard disk operations with `path.exists()` before `unlink()`.
- ✅ Store uploaded files with UUID filenames.
- ✅ Handle both form POST and XHR in upload endpoints (check `X-Requested-With` header).
- ✅ Use `await` for all I/O, `def` for pure computation.

### Don't
- ❌ Don't import `*` from any module.
- ❌ Don't use `except: pass` silently — either log or re-raise.
- ❌ Don't use ORMs — raw SQL via aiosqlite only.
- ❌ Don't put business logic in route handlers — delegate to services.
- ❌ Don't hardcode paths — use `Path(__file__).resolve()` relative paths or env vars.
- ❌ Don't add new translation files without updating `LANG_FLAGS` in `templates.py`.
- ❌ Don't use synchronous file I/O in hot paths (use `asyncio` subprocess for ffmpeg).
- ❌ Don't commit generated files (`__pycache__`, `.pyc`, `.db`, uploads) to git.
- ❌ Don't use `snake_case` in JS — use `camelCase` for JS functions and variables.
- ❌ Don't use `camelCase` in Python — use `snake_case` for everything.

---

## CSS Conventions

- **kebab-case** class names: `space-critical`, `seeker-controls`, `lang-dropdown`.
- **BEM-lite** prefixes: `btn-`, `seeker-`, `space-`, `lang-`.
- **Inline styles** are acceptable for dynamic/templated values in JS.
- **Responsive breakpoints**: 768px (tablet), 480px (mobile).
- **Colors**: dark navy nav (`#1a1a2e`), blue primary (`#4361ee`), red danger (`#e63946`).

---

## Git & Commit Style

- Commits follow descriptive sentence-style messages (not imperative).
- Current message example: `"fix: test for space available"`.
- `.gitignore` excludes: `venv/`, `__pycache__/`, `*.pyc`, `uploads/videos/*`, `uploads/thumbnails/*`, `data/*.db`, `.env`, `logs/`.

---

## One Inconsistency Noted

**Route URL naming** mixes plural and singular:
- Collection: `/api/videos` (plural) ✓
- Single resource: `/api/video/{id}/file` (singular) — should be `/api/videos/{id}/file` for consistency.

Prefer **plural for collections** (`/api/videos`, `/api/tags`) and **plural resource prefix** (`/api/videos/{id}/file`).
