# Match System Implementation Plan

**Goal:** Add basketball match tracking: CRUD, box-score stats, video-to-match linking, and a new match-centric home page.

**Architecture:** Flat schema — all box-score stats live as nullable columns on the `matches` table. `match_videos` join table links matches to videos. A pure Python `stats_calculator` module derives advanced stats (eFG%, TS%) from raw stats.

**Design:** `thoughts/shared/designs/2026-05-15-match-system-design.md`

---

## Checkpoint 1: Database + Backend

### Batch 1: Foundation (parallel — 3 implementers)

All tasks are independent — no project code dependencies between them.

#### Task 1.1: Database migration v5
**File:** `app/database.py` (edit)
**Test:** none (migration tested implicitly by conftest + test_matches)
**Depends:** none

Add the `matches` table, `match_videos` join table, and indexes as `MIGRATIONS[5]`.

**Implementation — `app/database.py` edit:**

After the existing `MIGRATIONS = { ... }` dict (at the end of line 62), add migration version 5:

```python
MATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    match_date TEXT NOT NULL,
    opponent TEXT DEFAULT '',
    location TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    minutes_played REAL,
    points INTEGER,
    two_point_attempts INTEGER,
    two_point_made INTEGER,
    three_point_attempts INTEGER,
    three_point_made INTEGER,
    free_throw_attempts INTEGER,
    free_throw_made INTEGER,
    offensive_rebounds INTEGER,
    defensive_rebounds INTEGER,
    total_rebounds INTEGER,
    assists INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    personal_fouls INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

MATCH_VIDEOS_TABLE = """
CREATE TABLE IF NOT EXISTS match_videos (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    UNIQUE(match_id, video_id)
);
"""

IDX_MATCHES_DATE = """
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date DESC);
"""

IDX_MATCH_VIDEOS_MATCH = """
CREATE INDEX IF NOT EXISTS idx_match_videos_match ON match_videos(match_id);
"""

IDX_MATCH_VIDEOS_VIDEO = """
CREATE INDEX IF NOT EXISTS idx_match_videos_video ON match_videos(video_id);
"""
```

Then edit the `MIGRATIONS` dict to add version 5:

```python
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    2: [],
    3: [TAGS_TABLE, VIDEO_TAGS_TABLE, IDX_VIDEO_TAGS_VIDEO, IDX_VIDEO_TAGS_TAG],
    4: [
        "ALTER TABLE videos ADD COLUMN source_video_id INTEGER REFERENCES videos(id)",
        "ALTER TABLE videos ADD COLUMN clip_start REAL",
        "ALTER TABLE videos ADD COLUMN clip_end REAL",
    ],
    5: [
        MATCHES_SCHEMA,
        MATCH_VIDEOS_TABLE,
        IDX_MATCHES_DATE,
        IDX_MATCH_VIDEOS_MATCH,
        IDX_MATCH_VIDEOS_VIDEO,
    ],
}
```

**Verify:** No explicit test; schema correctness is verified by conftest + test_matches.

---

#### Task 1.2: Stats Calculator
**File:** `app/services/stats_calculator.py` (new)
**Test:** `tests/test_matches.py` (TestStatsCalculator class — written in Task 4.1)
**Depends:** none

Pure functions for computing advanced basketball statistics. Zero DB or project imports.

**Implementation — `app/services/stats_calculator.py`:**

```python
"""
Pure functions for computing advanced basketball statistics.

Takes a raw stats dict from the matches table (snake_case fields)
and returns computed fields: percentages, eFG%, TS%.

All functions are pure — no DB access, no side effects.
"""


def compute_all(raw: dict) -> dict:
    """Compute derived stats from a raw box-score dict.

    Args:
        raw: Dict with snake_case match stat fields (may contain None).

    Returns:
        Dict with computed fields. Percentages are returned as
        float (0.0-100.0) or None if denominator is zero.
    """
    # Field access with None → 0 coercion
    two_pa = raw.get("two_point_attempts") or 0
    two_pm = raw.get("two_point_made") or 0
    three_pa = raw.get("three_point_attempts") or 0
    three_pm = raw.get("three_point_made") or 0
    fta = raw.get("free_throw_attempts") or 0
    ftm = raw.get("free_throw_made") or 0
    pts = raw.get("points") or 0

    fga = two_pa + three_pa
    fgm = two_pm + three_pm

    return {
        "fg_attempts": fga,
        "fg_made": fgm,
        "two_pct": _safe_pct(two_pm, two_pa),
        "three_pct": _safe_pct(three_pm, three_pa),
        "ft_pct": _safe_pct(ftm, fta),
        "efg_pct": _safe_efg(fgm, three_pm, fga),
        "ts_pct": _safe_ts(pts, fga, fta),
    }


def _safe_pct(made: int, attempts: int) -> float | None:
    """Return (made / attempts * 100) as float, or None if attempts == 0."""
    if attempts <= 0:
        return None
    return round((made / attempts) * 100, 1)


def _safe_efg(fgm: int, three_pm: int, fga: int) -> float | None:
    """Return effective field goal percentage * 100, or None if fga == 0.

    eFG% = (FGM + 0.5 * 3PM) / FGA
    """
    if fga <= 0:
        return None
    return round(((fgm + 0.5 * three_pm) / fga) * 100, 1)


def _safe_ts(pts: int, fga: int, fta: int) -> float | None:
    """Return true shooting percentage * 100, or None if denominator == 0.

    TS% = PTS / (2 * FGA + 0.44 * FTA)
    """
    denominator = 2 * fga + 0.44 * fta
    if denominator <= 0:
        return None
    return round((pts / denominator) * 100, 1)
```

---

#### Task 1.3: Route swap — `/` to `/videos`
**File:** `app/routes/videos.py` (edit)
**Test:** Existing tests update implicitly (Task 4.1 covers the swap)
**Depends:** none

Move the home page route from `GET /` to `GET /videos` and update all redirect targets.

**Edits:**

1. **Line 115:** Change `@router.get("/")` → `@router.get("/videos")`

2. **Line 200:** Change `"redirect": "/"` → `"redirect": "/videos"`

3. **Line 202:** Change `RedirectResponse(url="/", status_code=303)` → `RedirectResponse(url="/videos", status_code=303)`

4. **Line 291:** Change `return RedirectResponse(url="/", status_code=303)` → `return RedirectResponse(url="/videos", status_code=303)`

The route function `list_videos` at what was `GET /` now lives at `GET /videos`. The existing `GET /videos/{video_id}` detail route coexists without conflict (exact match `/videos` vs parameterized `/videos/{video_id}`).

---

### Batch 2: Core Service + Config (parallel — 2 implementers)

Depend on `database.py` schema existing (Batch 1).

#### Task 2.1: Match Service
**File:** `app/services/match_service.py` (new)
**Test:** `tests/test_matches.py` (TestMatchService class)
**Depends:** 1.1 (database schema)

CRUD operations for matches + video linking. Follows `video_service.py` pattern exactly: each function takes `db: aiosqlite.Connection` as first arg.

**Implementation — `app/services/match_service.py`:**

```python
"""
Business logic for match CRUD and video linking.

Each function takes an aiosqlite.Connection as the first argument.
This keeps them testable with in-memory databases.
"""

import logging

import aiosqlite

from app.services.stats_calculator import compute_all

logger = logging.getLogger(__name__)


async def create_match(
    db: aiosqlite.Connection,
    name: str,
    match_date: str,
    opponent: str = "",
    location: str = "",
    notes: str = "",
    **stats,
) -> dict:
    """Create a new match record.

    Args:
        db: Database connection.
        name: Match name/title (required).
        match_date: Date string (required, format YYYY-MM-DD).
        opponent: Opponent team name.
        location: Venue/location.
        notes: Free-text notes.
        **stats: Optional stat fields (points, assists, rebounds, etc.)

    Returns:
        Created match as dict.

    Raises:
        ValueError: If name or match_date is empty.
    """
    if not name or not name.strip():
        raise ValueError("Match name is required")
    if not match_date or not match_date.strip():
        raise ValueError("Match date is required")

    # Build INSERT with dynamic stat columns
    stat_fields = []
    stat_values = []
    for key in (
        "minutes_played", "points",
        "two_point_attempts", "two_point_made",
        "three_point_attempts", "three_point_made",
        "free_throw_attempts", "free_throw_made",
        "offensive_rebounds", "defensive_rebounds", "total_rebounds",
        "assists", "steals", "blocks", "turnovers", "personal_fouls",
    ):
        val = stats.get(key)
        stat_fields.append(key)
        stat_values.append(val if val is not None else None)  # Keep None as NULL

    columns = ", ".join(["name", "match_date", "opponent", "location", "notes"] + stat_fields)
    placeholders = ", ".join(["?"] * (5 + len(stat_fields)))
    values = [name.strip(), match_date.strip(), opponent, location, notes] + stat_values

    cursor = await db.execute(
        f"INSERT INTO matches ({columns}) VALUES ({placeholders})",
        values,
    )
    await db.commit()
    match_id = cursor.lastrowid
    logger.info("Match created: id=%d, name=%s", match_id, name)
    return await get_match(db, match_id)


async def get_match(db: aiosqlite.Connection, match_id: int) -> dict | None:
    """Fetch a single match by ID. Returns None if not found."""
    cursor = await db.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_matches(db: aiosqlite.Connection) -> list[dict]:
    """Return all matches ordered by match_date descending."""
    cursor = await db.execute(
        "SELECT * FROM matches ORDER BY match_date DESC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_match(db: aiosqlite.Connection, match_id: int, **fields) -> dict | None:
    """Update specified fields on a match.

    Accepts any match column as a keyword argument.
    Returns updated match dict, or None if match not found.
    """
    allowed_fields = {
        "name", "match_date", "opponent", "location", "notes",
        "minutes_played", "points",
        "two_point_attempts", "two_point_made",
        "three_point_attempts", "three_point_made",
        "free_throw_attempts", "free_throw_made",
        "offensive_rebounds", "defensive_rebounds", "total_rebounds",
        "assists", "steals", "blocks", "turnovers", "personal_fouls",
    }

    updates = {k: v for k, v in fields.items() if k in allowed_fields}
    if not updates:
        return await get_match(db, match_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [match_id]

    await db.execute(
        f"UPDATE matches SET {set_clause} WHERE id = ?",
        values,
    )
    await db.commit()
    logger.info("Match updated: id=%d, fields=%s", match_id, list(updates.keys()))
    return await get_match(db, match_id)


async def delete_match(db: aiosqlite.Connection, match_id: int) -> bool:
    """Delete a match. Returns True if deleted, False if not found.

    ON DELETE CASCADE cleans up match_videos associations automatically.
    """
    cursor = await db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Match deleted: id=%d", match_id)
    return deleted


async def link_video(db: aiosqlite.Connection, match_id: int, video_id: int):
    """Link a video to a match. Raises IntegrityError on duplicate."""
    await db.execute(
        "INSERT OR IGNORE INTO match_videos (match_id, video_id) VALUES (?, ?)",
        (match_id, video_id),
    )
    await db.commit()


async def unlink_video(db: aiosqlite.Connection, match_id: int, video_id: int):
    """Remove a video from a match."""
    await db.execute(
        "DELETE FROM match_videos WHERE match_id = ? AND video_id = ?",
        (match_id, video_id),
    )
    await db.commit()


async def get_match_with_videos(db: aiosqlite.Connection, match_id: int) -> dict | None:
    """Fetch a match along with its linked videos (each with tags)."""
    match = await get_match(db, match_id)
    if match is None:
        return None

    cursor = await db.execute(
        """SELECT v.* FROM videos v
           JOIN match_videos mv ON v.id = mv.video_id
           WHERE mv.match_id = ?
           ORDER BY v.upload_date DESC""",
        (match_id,),
    )
    videos = [dict(r) for r in await cursor.fetchall()]

    # Attach tags to each video
    from app.services.tag_service import get_video_tags
    for v in videos:
        v["tags"] = await get_video_tags(db, v["id"])

    match["videos"] = videos
    return match


async def get_match_with_stats(db: aiosqlite.Connection, match_id: int) -> dict | None:
    """Fetch a match with computed statistics.

    Returns dict with 'match' (raw) and 'computed' (derived stats).
    Returns None if match not found.
    """
    match = await get_match(db, match_id)
    if match is None:
        return None
    return {
        "match": match,
        "computed": compute_all(match),
    }


async def get_unlinked_videos(db: aiosqlite.Connection, match_id: int) -> list[dict]:
    """Return videos NOT already linked to this match.

    Used for the 'Link Video' picker UI.
    """
    cursor = await db.execute(
        """SELECT v.id, v.name, v.filename, v.mime_type
           FROM videos v
           WHERE v.id NOT IN (
               SELECT video_id FROM match_videos WHERE match_id = ?
           )
           ORDER BY v.upload_date DESC""",
        (match_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_video_matches(db: aiosqlite.Connection, video_id: int) -> list[dict]:
    """Return all matches that a video is linked to."""
    cursor = await db.execute(
        """SELECT m.id, m.name, m.match_date
           FROM matches m
           JOIN match_videos mv ON m.id = mv.match_id
           WHERE mv.video_id = ?
           ORDER BY m.match_date DESC""",
        (video_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
```

---

#### Task 2.2: Update conftest migration version
**File:** `tests/conftest.py` (edit)
**Test:** none (infrastructure)
**Depends:** 1.1

Bump the migration version range from 4 to 5 in the `db` fixture.

**Edit — `tests/conftest.py` line 35:**

```python
    for version in range(1, 6):  # migration_version=5 (includes match schema)
```

---

### Batch 3: Routes + App Wiring (parallel — 2 implementers)

Depend on `match_service.py` and `conftest.py` existing (Batch 2).

#### Task 3.1: Match Routes
**File:** `app/routes/matches.py` (new)
**Test:** `tests/test_matches.py` (TestMatchRoutes class)
**Depends:** 2.1, 2.2

All match HTTP endpoints. Follows `videos.py` route patterns: `Depends(get_db)`, `get_i18n(request)`, Jinja2 templates.

**Implementation — `app/routes/matches.py`:**

```python
"""
Match routes: list, create, detail, edit, delete, video linking.

Registers the home page (GET /) which now shows match list.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.services import match_service
from app.services.stats_calculator import compute_all
from app.templates import templates, get_i18n

router = APIRouter()

# Allowed stat field names for form parsing
_STAT_FIELDS = [
    "minutes_played", "points",
    "two_point_attempts", "two_point_made",
    "three_point_attempts", "three_point_made",
    "free_throw_attempts", "free_throw_made",
    "offensive_rebounds", "defensive_rebounds", "total_rebounds",
    "assists", "steals", "blocks", "turnovers", "personal_fouls",
]


def _parse_stat(value: str | None) -> int | float | None:
    """Parse a form field to int/float or None if empty/invalid."""
    if not value or not value.strip():
        return None
    try:
        # minutes_played is a REAL (float), everything else is INTEGER
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_match_form(form_data: dict) -> dict:
    """Extract match fields from form data, parsing stats as numbers."""
    fields = {
        "name": form_data.get("name", "").strip(),
        "match_date": form_data.get("match_date", "").strip(),
        "opponent": form_data.get("opponent", "").strip(),
        "location": form_data.get("location", "").strip(),
        "notes": form_data.get("notes", "").strip(),
    }
    for field in _STAT_FIELDS:
        fields[field] = _parse_stat(form_data.get(field))
    return fields


@router.get("/")
async def list_matches(request: Request, db=Depends(get_db)):
    """Home page — show all matches ordered by date descending."""
    i18n = get_i18n(request)
    matches = await match_service.list_matches(db)
    return templates.TemplateResponse(
        request,
        "match_list.html",
        {**i18n, "matches": matches},
    )


@router.get("/matches/new")
async def new_match_form(request: Request):
    """Show the create match form."""
    i18n = get_i18n(request)
    return templates.TemplateResponse(
        request,
        "match_form.html",
        {**i18n, "match": None},
    )


@router.post("/api/matches")
async def create_match(request: Request, db=Depends(get_db)):
    """Create a new match from form data."""
    i18n = get_i18n(request)
    form = await request.form()
    fields = _parse_match_form(dict(form))

    # Validate required fields
    errors = []
    if not fields["name"]:
        errors.append("Match name is required")
    if not fields["match_date"]:
        errors.append("Match date is required")

    if errors:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": fields, "errors": errors},
            status_code=400,
        )

    # Separate stat fields from metadata
    name = fields.pop("name")
    match_date = fields.pop("match_date")
    opponent = fields.pop("opponent")
    location = fields.pop("location")
    notes = fields.pop("notes")
    stats = {k: fields[k] for k in _STAT_FIELDS}

    try:
        match = await match_service.create_match(
            db, name=name, match_date=match_date,
            opponent=opponent, location=location, notes=notes,
            **stats,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": {**fields, "name": name, "match_date": match_date}, "errors": [str(e)]},
            status_code=400,
        )

    return RedirectResponse(url=f"/matches/{match['id']}", status_code=303)


@router.get("/matches/{match_id}")
async def match_detail(request: Request, match_id: int, db=Depends(get_db)):
    """Match detail page with stats and linked videos."""
    i18n = get_i18n(request)
    result = await match_service.get_match_with_videos(db, match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Match not found")

    computed = compute_all(result)
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "match_detail.html",
        {**i18n, "match": result, "computed": computed, "unlinked_videos": unlinked},
    )


@router.get("/matches/{match_id}/edit")
async def edit_match_form(request: Request, match_id: int, db=Depends(get_db)):
    """Show the edit match form."""
    i18n = get_i18n(request)
    match = await match_service.get_match(db, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    return templates.TemplateResponse(
        request,
        "match_form.html",
        {**i18n, "match": match},
    )


@router.post("/api/matches/{match_id}")
async def update_match(request: Request, match_id: int, db=Depends(get_db)):
    """Update an existing match."""
    i18n = get_i18n(request)

    # Verify match exists
    existing = await match_service.get_match(db, match_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Match not found")

    form = await request.form()
    fields = _parse_match_form(dict(form))

    if not fields["name"]:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": {**existing, **fields}, "errors": ["Match name is required"]},
            status_code=400,
        )

    await match_service.update_match(db, match_id, **fields)
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/delete")
async def delete_match(match_id: int, db=Depends(get_db)):
    """Delete a match and its associations."""
    deleted = await match_service.delete_match(db, match_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Match not found")
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/matches/{match_id}/videos")
async def link_video(
    request: Request,
    match_id: int,
    video_id: int = Form(...),
    db=Depends(get_db),
):
    """Link a video to a match. Returns HTMX fragment."""
    i18n = get_i18n(request)

    # Verify match exists
    match = await match_service.get_match(db, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    await match_service.link_video(db, match_id, video_id)

    # Refresh data for HTMX fragment re-render
    result = await match_service.get_match_with_videos(db, match_id)
    computed = compute_all(result or {})
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "_match_videos.html",
        {
            **i18n,
            "match": {"id": match_id, "videos": result.get("videos", []) if result else []},
            "computed": computed,
            "unlinked_videos": unlinked,
        },
    )


@router.post("/api/matches/{match_id}/videos/{video_id}/remove")
async def unlink_video(
    request: Request,
    match_id: int,
    video_id: int,
    db=Depends(get_db),
):
    """Remove a video from a match. Returns HTMX fragment."""
    i18n = get_i18n(request)
    await match_service.unlink_video(db, match_id, video_id)

    # Refresh data for HTMX fragment re-render
    result = await match_service.get_match_with_videos(db, match_id)
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "_match_videos.html",
        {
            **i18n,
            "match": {"id": match_id, "videos": result.get("videos", []) if result else []},
            "unlinked_videos": unlinked,
        },
    )
```

---

#### Task 3.2: Register match router in main.py
**File:** `app/main.py` (edit)
**Test:** none (verified by test_matches route tests)
**Depends:** 2.2 (migration version), 3.1 must exist (imported at runtime)

Two changes:
1. Bump `init_db` migration version to 5
2. Import and include the matches router

**Edit 1 — `app/main.py` line 26 (add import):**

```python
from app.routes.matches import router as matches_router
```

**Edit 2 — `app/main.py` line 55 (add include_router after tags):**

```python
app.include_router(videos_router)
app.include_router(tags_router)
app.include_router(matches_router)
```

**Edit 3 — `app/main.py` line 139 (bump migration):**

```python
await init_db(migration_version=5)
```

---

### Batch 4: Backend Tests (1 implementer)

#### Task 4.1: Match Tests (Backend)
**File:** `tests/test_matches.py` (new)
**Depends:** 3.1, 3.2 (routes must compile), 1.2 (stats_calculator)

Comprehensive tests for stats calculator, match service, and match routes.

**Implementation — `tests/test_matches.py`:**

```python
"""
Tests for match system — stats calculator, service CRUD, and HTTP routes.

Run with: pytest tests/test_matches.py -v
"""

import pytest
from tests.conftest import create_test_video


class TestStatsCalculator:
    """Tests for pure stats computation functions (no DB needed)."""

    @pytest.mark.asyncio
    async def test_all_formulas(self):
        """All 7 formulas produce correct values given known inputs."""
        from app.services.stats_calculator import compute_all

        raw = {
            "minutes_played": 32.5,
            "points": 24,
            "two_point_attempts": 10,
            "two_point_made": 6,
            "three_point_attempts": 5,
            "three_point_made": 3,
            "free_throw_attempts": 4,
            "free_throw_made": 3,
            "offensive_rebounds": 2,
            "defensive_rebounds": 5,
            "total_rebounds": 7,
            "assists": 4,
            "steals": 1,
            "blocks": 0,
            "turnovers": 2,
            "personal_fouls": 3,
        }
        c = compute_all(raw)
        assert c["fg_attempts"] == 15      # 10 + 5
        assert c["fg_made"] == 9           # 6 + 3
        assert c["two_pct"] == 60.0         # 6/10 * 100
        assert c["three_pct"] == 60.0       # 3/5 * 100
        assert c["ft_pct"] == 75.0          # 3/4 * 100
        assert c["efg_pct"] == 70.0         # (9 + 0.5*3) / 15 * 100
        # TS% = 24 / (2*15 + 0.44*4) * 100
        expected_ts = 24 / (30 + 1.76) * 100
        assert c["ts_pct"] == pytest.approx(expected_ts, rel=1e-3)

    @pytest.mark.asyncio
    async def test_zero_division_returns_none(self):
        """All percentages return None when denominator is zero."""
        from app.services.stats_calculator import compute_all

        raw = {
            "points": 0,
            "two_point_attempts": 0,
            "two_point_made": 0,
            "three_point_attempts": 0,
            "three_point_made": 0,
            "free_throw_attempts": 0,
            "free_throw_made": 0,
        }
        c = compute_all(raw)
        assert c["two_pct"] is None
        assert c["three_pct"] is None
        assert c["ft_pct"] is None
        assert c["efg_pct"] is None
        assert c["ts_pct"] is None

    @pytest.mark.asyncio
    async def test_missing_fields_default_to_zero(self):
        """Empty/partial dicts don't crash — missing keys treated as 0."""
        from app.services.stats_calculator import compute_all

        c = compute_all({})
        assert c["fg_attempts"] == 0
        assert c["fg_made"] == 0
        assert c["two_pct"] is None
        assert c["three_pct"] is None
        assert c["ft_pct"] is None
        assert c["efg_pct"] is None
        assert c["ts_pct"] is None

    @pytest.mark.asyncio
    async def test_partial_stats(self):
        """Some fields filled, others None — works correctly."""
        from app.services.stats_calculator import compute_all

        raw = {
            "points": 10,
            "two_point_attempts": 8,
            "two_point_made": 4,
            "three_point_attempts": 0,
            "three_point_made": 0,
            "free_throw_attempts": 2,
            "free_throw_made": 2,
        }
        c = compute_all(raw)
        assert c["fg_attempts"] == 8
        assert c["two_pct"] == 50.0
        assert c["three_pct"] is None  # 0 attempts
        assert c["ft_pct"] == 100.0


class TestMatchService:
    """Tests for match_service CRUD operations (uses db fixture directly)."""

    @pytest.mark.asyncio
    async def test_create_match(self, db):
        """Valid match creates a DB record with correct fields."""
        from app.services.match_service import create_match, get_match

        match = await create_match(db, name="Test Match", match_date="2026-05-15")
        assert match["id"] >= 1
        assert match["name"] == "Test Match"
        assert match["match_date"] == "2026-05-15"
        assert match["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_match_with_optional_fields(self, db):
        """Create match with opponent, location, and stat values."""
        from app.services.match_service import create_match

        match = await create_match(
            db,
            name="Full Match",
            match_date="2026-05-15",
            opponent="Rivals",
            location="Home Court",
            points=24,
            assists=5,
            minutes_played=32.5,
        )
        assert match["opponent"] == "Rivals"
        assert match["location"] == "Home Court"
        assert match["points"] == 24
        assert match["assists"] == 5
        assert match["minutes_played"] == 32.5

    @pytest.mark.asyncio
    async def test_create_match_missing_name_raises(self, db):
        """Missing name raises ValueError."""
        from app.services.match_service import create_match

        with pytest.raises(ValueError, match="required"):
            await create_match(db, name="", match_date="2026-05-15")

    @pytest.mark.asyncio
    async def test_create_match_missing_date_raises(self, db):
        """Missing match_date raises ValueError."""
        from app.services.match_service import create_match

        with pytest.raises(ValueError, match="required"):
            await create_match(db, name="Test", match_date="")

    @pytest.mark.asyncio
    async def test_get_match_not_found(self, db):
        """get_match returns None for non-existent id."""
        from app.services.match_service import get_match

        match = await get_match(db, 9999)
        assert match is None

    @pytest.mark.asyncio
    async def test_list_matches_empty(self, db):
        """list_matches returns empty list when no matches exist."""
        from app.services.match_service import list_matches

        matches = await list_matches(db)
        assert matches == []

    @pytest.mark.asyncio
    async def test_list_matches_order_by_date_desc(self, db):
        """list_matches returns newest match first."""
        from app.services.match_service import create_match, list_matches

        await create_match(db, name="Older", match_date="2026-05-01")
        await create_match(db, name="Newer", match_date="2026-05-15")

        matches = await list_matches(db)
        assert len(matches) == 2
        assert matches[0]["name"] == "Newer"
        assert matches[1]["name"] == "Older"

    @pytest.mark.asyncio
    async def test_update_match_name_date(self, db):
        """update_match changes name and date."""
        from app.services.match_service import create_match, update_match, get_match

        match = await create_match(db, name="Original", match_date="2026-05-01")
        await update_match(db, match["id"], name="Updated", match_date="2026-05-20")
        updated = await get_match(db, match["id"])
        assert updated["name"] == "Updated"
        assert updated["match_date"] == "2026-05-20"

    @pytest.mark.asyncio
    async def test_update_match_stats(self, db):
        """update_match changes individual stat fields."""
        from app.services.match_service import create_match, update_match, get_match

        match = await create_match(db, name="Stats Update", match_date="2026-05-15")
        await update_match(db, match["id"], points=30, assists=10)
        updated = await get_match(db, match["id"])
        assert updated["points"] == 30
        assert updated["assists"] == 10
        assert updated["name"] == "Stats Update"  # unchanged

    @pytest.mark.asyncio
    async def test_delete_match(self, db):
        """delete_match removes the match record."""
        from app.services.match_service import create_match, delete_match, get_match

        match = await create_match(db, name="To Delete", match_date="2026-05-15")
        assert await get_match(db, match["id"]) is not None

        result = await delete_match(db, match["id"])
        assert result is True
        assert await get_match(db, match["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_match_not_found(self, db):
        """delete_match returns False for non-existent id."""
        from app.services.match_service import delete_match

        result = await delete_match(db, 9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_match_cascade_cleans_up(self, db):
        """Deleting a match removes match_videos associations (CASCADE)."""
        from app.services.match_service import create_match, link_video, delete_match

        # Create match + video
        match = await create_match(db, name="Cascade", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Vid", "v.mp4", "v.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        # Verify link exists
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM match_videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

        # Delete match
        await delete_match(db, match["id"])

        # Verify link is gone
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM match_videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 0

        # Verify video survives
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    @pytest.mark.asyncio
    async def test_link_video(self, db):
        """link_video creates association between match and video."""
        from app.services.match_service import create_match, link_video

        match = await create_match(db, name="Link Test", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Linked", "l.mp4", "l.mp4", "video/mp4", 100),
        )
        await db.commit()

        await link_video(db, match["id"], 1)

        cursor = await db.execute(
            "SELECT * FROM match_videos WHERE match_id=? AND video_id=?",
            (match["id"], 1),
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_unlink_video(self, db):
        """unlink_video removes association, other associations survive."""
        from app.services.match_service import create_match, link_video, unlink_video

        match = await create_match(db, name="Unlink Test", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("V1", "v1.mp4", "v1.mp4", "video/mp4", 100),
        )
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("V2", "v2.mp4", "v2.mp4", "video/mp4", 100),
        )
        await db.commit()

        await link_video(db, match["id"], 1)
        await link_video(db, match["id"], 2)

        await unlink_video(db, match["id"], 1)

        cursor = await db.execute(
            "SELECT video_id FROM match_videos WHERE match_id=?",
            (match["id"],),
        )
        rows = await cursor.fetchall()
        remaining = [r["video_id"] for r in rows]
        assert remaining == [2]

    @pytest.mark.asyncio
    async def test_get_match_with_videos(self, db):
        """get_match_with_videos returns match with enriched video list."""
        from app.services.match_service import create_match, link_video, get_match_with_videos

        match = await create_match(db, name="With Videos", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("My Video", "mv.mp4", "mv.mp4", "video/mp4", 200),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        result = await get_match_with_videos(db, match["id"])
        assert result is not None
        assert result["name"] == "With Videos"
        assert len(result["videos"]) == 1
        assert result["videos"][0]["name"] == "My Video"

    @pytest.mark.asyncio
    async def test_get_match_with_videos_not_found(self, db):
        """get_match_with_videos returns None for bad id."""
        from app.services.match_service import get_match_with_videos

        result = await get_match_with_videos(db, 9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_unlinked_videos(self, db):
        """get_unlinked_videos returns only videos not linked to match."""
        from app.services.match_service import create_match, link_video, get_unlinked_videos

        match = await create_match(db, name="Unlinked", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("LinkedVid", "l.mp4", "l.mp4", "video/mp4", 100),
        )
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("FreeVid", "f.mp4", "f.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        unlinked = await get_unlinked_videos(db, match["id"])
        assert len(unlinked) == 1
        assert unlinked[0]["name"] == "FreeVid"

    @pytest.mark.asyncio
    async def test_get_video_matches(self, db):
        """get_video_matches returns matches a video belongs to."""
        from app.services.match_service import create_match, link_video, get_video_matches

        m1 = await create_match(db, name="Match A", match_date="2026-05-01")
        m2 = await create_match(db, name="Match B", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Shared", "s.mp4", "s.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, m1["id"], 1)
        await link_video(db, m2["id"], 1)

        matches = await get_video_matches(db, 1)
        assert len(matches) == 2
        assert matches[0]["name"] == "Match B"  # newest first


class TestMatchRoutes:
    """Tests for match HTTP endpoints (uses client fixture)."""

    @pytest.mark.asyncio
    async def test_home_page_returns_match_list(self, client):
        """GET / returns 200 and shows match-related content."""
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_videos_page_still_accessible(self, client):
        """GET /videos returns the video grid (old home behavior preserved)."""
        response = await client.get("/videos")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_match_via_route(self, client):
        """POST /api/matches creates a match and redirects to detail."""
        response = await client.post(
            "/api/matches",
            data={"name": "Route Match", "match_date": "2026-05-15"},
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/matches/")

    @pytest.mark.asyncio
    async def test_create_match_missing_name(self, client):
        """POST /api/matches without name returns 400."""
        response = await client.post(
            "/api/matches",
            data={"match_date": "2026-05-15"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_match_detail_page(self, client):
        """GET /matches/{id} shows match detail."""
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Detail Test", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 200
        assert "Detail Test" in detail.text

    @pytest.mark.asyncio
    async def test_match_detail_not_found(self, client):
        """GET /matches/999 returns 404."""
        response = await client.get("/matches/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_new_match_form(self, client):
        """GET /matches/new shows create form."""
        response = await client.get("/matches/new")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edit_match_form(self, client):
        """GET /matches/{id}/edit shows edit form with match data."""
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Edit Me", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        edit_page = await client.get(f"/matches/{match_id}/edit")
        assert edit_page.status_code == 200
        assert "Edit Me" in edit_page.text

    @pytest.mark.asyncio
    async def test_update_match_via_route(self, client):
        """POST /api/matches/{id} updates match and redirects."""
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Before", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        await client.post(
            f"/api/matches/{match_id}",
            data={"name": "After Update", "match_date": "2026-05-16", "points": "30"},
        )

        detail = await client.get(f"/matches/{match_id}")
        assert "After Update" in detail.text

    @pytest.mark.asyncio
    async def test_delete_match_via_route(self, client):
        """POST /matches/{id}/delete deletes and redirects to home."""
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Delete Me", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        delete_resp = await client.post(f"/matches/{match_id}/delete")
        assert delete_resp.status_code == 303
        assert delete_resp.headers["location"] == "/"

        # Verify gone
        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_match_not_found(self, client):
        """POST /matches/999/delete returns 404."""
        response = await client.post("/matches/999/delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_video_round_trip(self, client):
        """Link a video, then verify via GET /videos that route still works."""
        # Create a video
        video_id = await create_test_video(client, "Linkable Video", "")

        # Create a match
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Video Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link the video
        link_resp = await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
        )
        assert link_resp.status_code == 200

        # Verify on match detail
        detail = await client.get(f"/matches/{match_id}")
        assert "Linkable Video" in detail.text

    @pytest.mark.asyncio
    async def test_unlink_video_round_trip(self, client):
        """Link a video, unlink it, verify it's gone."""
        video_id = await create_test_video(client, "Removable Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Remove Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link
        await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
        )

        # Unlink
        remove_resp = await client.post(
            f"/api/matches/{match_id}/videos/{video_id}/remove",
        )
        assert remove_resp.status_code == 200

        # Verify gone from detail
        detail = await client.get(f"/matches/{match_id}")
        assert "Removable Video" not in detail.text

    @pytest.mark.asyncio
    async def test_match_detail_shows_stats(self, client):
        """Match detail page includes stats table."""
        create_resp = await client.post(
            "/api/matches",
            data={
                "name": "Stats Display",
                "match_date": "2026-05-15",
                "points": "24",
                "two_point_attempts": "10",
                "two_point_made": "6",
                "three_point_attempts": "5",
                "three_point_made": "3",
            },
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        # Stats table should be present
        assert "PTS" in detail.text
        assert "24" in detail.text
        assert "FG%" in detail.text or "FG" in detail.text
```

**Verify:** `bun test tests/test_matches.py -v` (or `python -m pytest tests/test_matches.py -v`)

---

### Checkpoint 1 STOP — Validate with user

Run `python -m pytest tests/test_matches.py -v` and confirm all tests pass.
Run `python -m pytest tests/test_videos.py -v` and confirm existing tests still pass.

---

## Checkpoint 2: Frontend

### Batch 5: i18n Translations (parallel — 2 implementers)

No dependencies on project code.

#### Task 5.1: English translations
**File:** `translations/en.json` (edit)
**Depends:** none

Append match-related translation keys at the end of the file.

**Edit — append to `translations/en.json`:**

```json
  "nav.videos": "Videos",

  "page.matches": "Matches",

  "match.no_matches": "No matches yet.",
  "match.create_first": "Create your first match",
  "match.back_to_list": "← Back to matches",
  "match.box_score": "Box Score",
  "match.advanced_stats": "Advanced Stats",
  "match.videos": "Videos",
  "match.no_videos": "No videos linked to this match.",
  "match.link_video": "Link Video",
  "match.remove_video": "Remove",
  "match.confirm_delete": "Delete this match? Videos linked to it will be preserved.",
  "match.new": "New Match",
  "match.edit": "Edit Match",
  "match.form.name": "Match Name",
  "match.form.date": "Date",
  "match.form.opponent": "Opponent",
  "match.form.location": "Location",
  "match.form.notes": "Notes",
  "match.form.save": "Save Match",
  "match.form.cancel": "Cancel",
  "match.video_belongs_to": "Part of match:",
  "match.linked_matches": "Matches",

  "stat.mp": "MP",
  "stat.pts": "PTS",
  "stat.fga": "FGA",
  "stat.fgm": "FGM",
  "stat.fg_pct": "FG%",
  "stat.two_pa": "2PA",
  "stat.two_pm": "2PM",
  "stat.two_pct": "2P%",
  "stat.three_pa": "3PA",
  "stat.three_pm": "3PM",
  "stat.three_pct": "3P%",
  "stat.fta": "FTA",
  "stat.ftm": "FTM",
  "stat.ft_pct": "FT%",
  "stat.orb": "ORB",
  "stat.drb": "DRB",
  "stat.trb": "TRB",
  "stat.ast": "AST",
  "stat.stl": "STL",
  "stat.blk": "BLK",
  "stat.tov": "TOV",
  "stat.pf": "PF",
  "stat.efg": "eFG%",
  "stat.ts": "TS%"
}
```

**Verify:** `python -c "import json; json.load(open('translations/en.json')); print('OK')"`

---

#### Task 5.2: French translations
**File:** `translations/fr.json` (edit)
**Depends:** none

Append French translations for all match keys.

**Edit — append to `translations/fr.json`:**

```json
  "nav.videos": "Vidéos",

  "page.matches": "Matchs",

  "match.no_matches": "Aucun match pour le moment.",
  "match.create_first": "Créer votre premier match",
  "match.back_to_list": "← Retour aux matchs",
  "match.box_score": "Statistiques",
  "match.advanced_stats": "Statistiques avancées",
  "match.videos": "Vidéos",
  "match.no_videos": "Aucune vidéo liée à ce match.",
  "match.link_video": "Lier une vidéo",
  "match.remove_video": "Retirer",
  "match.confirm_delete": "Supprimer ce match ? Les vidéos liées seront conservées.",
  "match.new": "Nouveau match",
  "match.edit": "Modifier le match",
  "match.form.name": "Nom du match",
  "match.form.date": "Date",
  "match.form.opponent": "Adversaire",
  "match.form.location": "Lieu",
  "match.form.notes": "Notes",
  "match.form.save": "Enregistrer le match",
  "match.form.cancel": "Annuler",
  "match.video_belongs_to": "Fait partie du match :",
  "match.linked_matches": "Matchs",

  "stat.mp": "MP",
  "stat.pts": "PTS",
  "stat.fga": "TFS",
  "stat.fgm": "TFR",
  "stat.fg_pct": "TF%",
  "stat.two_pa": "2PT",
  "stat.two_pm": "2PR",
  "stat.two_pct": "2P%",
  "stat.three_pa": "3PT",
  "stat.three_pm": "3PR",
  "stat.three_pct": "3P%",
  "stat.fta": "LF",
  "stat.ftm": "LFR",
  "stat.ft_pct": "LF%",
  "stat.orb": "ORB",
  "stat.drb": "DRB",
  "stat.trb": "TRB",
  "stat.ast": "PAS",
  "stat.stl": "INT",
  "stat.blk": "CON",
  "stat.tov": "PTP",
  "stat.pf": "FTS",
  "stat.efg": "eFG%",
  "stat.ts": "TS%"
}
```

**Verify:** `python -c "import json; json.load(open('translations/fr.json')); print('OK')"`

---

### Batch 6: Templates + CSS (parallel — 9 implementers)

No dependencies between template files — all can be created simultaneously. Templates use `_()` for i18n, `current_lang`, `current_flag` from context. Each is a complete Jinja2 file.

#### Task 6.1: `match_list.html`
**File:** `app/templates/match_list.html` (new)
**Depends:** none

Home page showing match cards in a responsive grid.

```html
{% extends "base.html" %}
{% block title %}{{ _("page.matches") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ _("page.matches") }}</h1>
    <div class="actions">
        <a href="/matches/new" class="btn btn-primary">{{ _("match.new") }}</a>
    </div>
</div>

{% if matches and matches|length > 0 %}
<div class="match-grid">
    {% for match in matches %}
    <div class="match-card">
        <a href="/matches/{{ match.id }}" class="match-card-link">
            <h3 class="match-card-title">{{ match.name }}</h3>
            <div class="match-card-meta">
                <span class="match-card-date">{{ match.match_date }}</span>
                {% if match.opponent %}
                <span class="match-card-opponent">{{ _("match.form.opponent") }}: {{ match.opponent }}</span>
                {% endif %}
                {% if match.location %}
                <span class="match-card-location">{{ match.location }}</span>
                {% endif %}
            </div>
            {% if match.points is not none %}
            <div class="match-card-stats">
                <span class="stat-highlight">{{ match.points }} {{ _("stat.pts") }}</span>
                {% if match.assists is not none %}
                <span>{{ match.assists }} {{ _("stat.ast") }}</span>
                {% endif %}
                {% if match.total_rebounds is not none %}
                <span>{{ match.total_rebounds }} {{ _("stat.trb") }}</span>
                {% endif %}
            </div>
            {% endif %}
        </a>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="empty-state">
    <p>{{ _("match.no_matches") }}</p>
    <a href="/matches/new" class="btn btn-primary">{{ _("match.create_first") }}</a>
</div>
{% endif %}
{% endblock %}
```

---

#### Task 6.2: `match_detail.html`
**File:** `app/templates/match_detail.html` (new)
**Depends:** none

Full match detail page with stats table, advanced stats, and linked videos section.

```html
{% extends "base.html" %}
{% block title %}{{ match.name }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="page-header">
    <div>
        <a href="/" style="color: #4361ee; text-decoration: none; display: inline-block; margin-bottom: 0.5rem;">{{ _("match.back_to_list") }}</a>
        <h1 style="margin-bottom: 0.25rem;">{{ match.name }}</h1>
        <p style="color: #888; font-size: 0.9rem;">
            {{ match.match_date }}
            {% if match.opponent %} &middot; vs {{ match.opponent }}{% endif %}
            {% if match.location %} &middot; {{ match.location }}{% endif %}
        </p>
    </div>
    <div class="actions">
        <a href="/matches/{{ match.id }}/edit" class="btn btn-primary btn-sm">{{ _("btn.edit") }}</a>
        <form action="/matches/{{ match.id }}/delete" method="post" style="display: inline;"
              onsubmit="return confirm('{{ _("match.confirm_delete") }}')">
            <button type="submit" class="btn btn-danger btn-sm">{{ _("btn.delete") }}</button>
        </form>
    </div>
</div>

{% if match.notes %}
<div style="margin-bottom: 1.5rem; padding: 0.75rem; background: #f9f9f9; border-radius: 6px; color: #555;">
    {{ match.notes }}
</div>
{% endif %}

{% include "_match_stats.html" %}

<h2 style="margin-top: 2rem; margin-bottom: 0.75rem;">{{ _("match.videos") }}</h2>
<div id="match-videos-section">
    {% include "_match_videos.html" %}
</div>
{% endblock %}
```

---

#### Task 6.3: `match_form.html`
**File:** `app/templates/match_form.html` (new)
**Depends:** none

Dual-purpose create/edit form. When `match` is None, it's a create form; otherwise it's prefilled for editing.

```html
{% extends "base.html" %}
{% block title %}{% if match %}{{ _("match.edit") }}{% else %}{{ _("match.new") }}{% endif %} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<h1 style="margin-bottom: 1.5rem;">{% if match %}{{ _("match.edit") }}{% else %}{{ _("match.new") }}{% endif %}</h1>

{% if errors and errors|length > 0 %}
<div class="error">
    {% for err in errors %}
    <p>{{ err }}</p>
    {% endfor %}
</div>
{% endif %}

<form action="{% if match %}/api/matches/{{ match.id }}{% else %}/api/matches{% endif %}" method="post">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div>
            <label>{{ _("match.form.name") }}</label>
            <input type="text" name="name" value="{{ match.name if match else '' }}" required>
        </div>
        <div>
            <label>{{ _("match.form.date") }}</label>
            <input type="date" name="match_date" value="{{ match.match_date if match else '' }}" required>
        </div>
        <div>
            <label>{{ _("match.form.opponent") }}</label>
            <input type="text" name="opponent" value="{{ match.opponent if match else '' }}">
        </div>
        <div>
            <label>{{ _("match.form.location") }}</label>
            <input type="text" name="location" value="{{ match.location if match else '' }}">
        </div>
    </div>

    <h3 style="margin-top: 1.5rem; margin-bottom: 0.75rem;">{{ _("match.box_score") }}</h3>
    <div class="stats-form-grid">
        <div class="stat-field">
            <label>{{ _("stat.mp") }}</label>
            <input type="number" name="minutes_played" step="0.1" min="0"
                   value="{{ match.minutes_played if match and match.minutes_played is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.pts") }}</label>
            <input type="number" name="points" min="0"
                   value="{{ match.points if match and match.points is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.two_pa") }}</label>
            <input type="number" name="two_point_attempts" min="0"
                   value="{{ match.two_point_attempts if match and match.two_point_attempts is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.two_pm") }}</label>
            <input type="number" name="two_point_made" min="0"
                   value="{{ match.two_point_made if match and match.two_point_made is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.three_pa") }}</label>
            <input type="number" name="three_point_attempts" min="0"
                   value="{{ match.three_point_attempts if match and match.three_point_attempts is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.three_pm") }}</label>
            <input type="number" name="three_point_made" min="0"
                   value="{{ match.three_point_made if match and match.three_point_made is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.fta") }}</label>
            <input type="number" name="free_throw_attempts" min="0"
                   value="{{ match.free_throw_attempts if match and match.free_throw_attempts is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.ftm") }}</label>
            <input type="number" name="free_throw_made" min="0"
                   value="{{ match.free_throw_made if match and match.free_throw_made is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.orb") }}</label>
            <input type="number" name="offensive_rebounds" min="0"
                   value="{{ match.offensive_rebounds if match and match.offensive_rebounds is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.drb") }}</label>
            <input type="number" name="defensive_rebounds" min="0"
                   value="{{ match.defensive_rebounds if match and match.defensive_rebounds is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.trb") }}</label>
            <input type="number" name="total_rebounds" min="0"
                   value="{{ match.total_rebounds if match and match.total_rebounds is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.ast") }}</label>
            <input type="number" name="assists" min="0"
                   value="{{ match.assists if match and match.assists is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.stl") }}</label>
            <input type="number" name="steals" min="0"
                   value="{{ match.steals if match and match.steals is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.blk") }}</label>
            <input type="number" name="blocks" min="0"
                   value="{{ match.blocks if match and match.blocks is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.tov") }}</label>
            <input type="number" name="turnovers" min="0"
                   value="{{ match.turnovers if match and match.turnovers is not none else '' }}">
        </div>
        <div class="stat-field">
            <label>{{ _("stat.pf") }}</label>
            <input type="number" name="personal_fouls" min="0"
                   value="{{ match.personal_fouls if match and match.personal_fouls is not none else '' }}">
        </div>
    </div>

    <div style="margin-top: 1.5rem;">
        <label>{{ _("match.form.notes") }}</label>
        <textarea name="notes" rows="3" style="width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 6px; font-family: inherit; resize: vertical;">{{ match.notes if match else '' }}</textarea>
    </div>

    <div style="margin-top: 1.5rem; display: flex; gap: 0.75rem;">
        <button type="submit" class="btn btn-primary">{{ _("match.form.save") }}</button>
        <a href="/{% if match %}matches/{{ match.id }}{% endif %}" class="btn btn-inactive">{{ _("match.form.cancel") }}</a>
    </div>
</form>
{% endblock %}
```

---

#### Task 6.4: `_match_card.html`
**File:** `app/templates/_match_card.html` (new)
**Depends:** none

Individual match card fragment (used by match_list.html inline/include; kept as standalone for future HTMX lazy-loading).

```html
<div class="match-card">
    <a href="/matches/{{ match.id }}" class="match-card-link">
        <h3 class="match-card-title">{{ match.name }}</h3>
        <div class="match-card-meta">
            <span class="match-card-date">{{ match.match_date }}</span>
            {% if match.opponent %}
            <span class="match-card-opponent">vs {{ match.opponent }}</span>
            {% endif %}
            {% if match.location %}
            <span class="match-card-location">{{ match.location }}</span>
            {% endif %}
        </div>
        {% if match.points is not none %}
        <div class="match-card-stats">
            <span class="stat-highlight">{{ match.points }} {{ _("stat.pts") }}</span>
            {% if match.assists is not none %}
            <span>{{ match.assists }} {{ _("stat.ast") }}</span>
            {% endif %}
            {% if match.total_rebounds is not none %}
            <span>{{ match.total_rebounds }} {{ _("stat.trb") }}</span>
            {% endif %}
        </div>
        {% endif %}
    </a>
</div>
```

---

#### Task 6.5: `_match_videos.html` (basic version)
**File:** `app/templates/_match_videos.html` (new)
**Depends:** none

Basic read-only version for CP2. Shows linked videos. CP3 will add Link/Remove buttons.

```html
{% if match.videos and match.videos|length > 0 %}
<div class="linked-videos">
    {% for video in match.videos %}
    <div class="linked-video-item">
        <a href="/videos/{{ video.id }}" class="linked-video-link">{{ video.name }}</a>
        {% if video.tags and video.tags|length > 0 %}
        <div class="video-tags">
            {% for tag in video.tags %}
            <span class="tag-badge">{{ tag }}</span>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    {% endfor %}
</div>
{% else %}
<p style="color: #888;">{{ _("match.no_videos") }}</p>
{% endif %}
```

---

#### Task 6.6: `_match_stats.html`
**File:** `app/templates/_match_stats.html` (new)
**Depends:** none

Box score table and advanced stats. Computed `computed` dict contains derived stats. Template handles None values by displaying "—".

```html
<div id="match-stats">
    <h3 style="margin-bottom: 0.75rem;">{{ _("match.box_score") }}</h3>
    <div class="stats-table-wrapper">
        <table class="stats-table">
            <thead>
                <tr>
                    <th>{{ _("stat.mp") }}</th>
                    <th>{{ _("stat.pts") }}</th>
                    <th>{{ _("stat.fga") }}</th>
                    <th>{{ _("stat.fgm") }}</th>
                    <th>{{ _("stat.fg_pct") }}</th>
                    <th>{{ _("stat.two_pa") }}</th>
                    <th>{{ _("stat.two_pm") }}</th>
                    <th>{{ _("stat.two_pct") }}</th>
                    <th>{{ _("stat.three_pa") }}</th>
                    <th>{{ _("stat.three_pm") }}</th>
                    <th>{{ _("stat.three_pct") }}</th>
                    <th>{{ _("stat.fta") }}</th>
                    <th>{{ _("stat.ftm") }}</th>
                    <th>{{ _("stat.ft_pct") }}</th>
                    <th>{{ _("stat.orb") }}</th>
                    <th>{{ _("stat.drb") }}</th>
                    <th>{{ _("stat.trb") }}</th>
                    <th>{{ _("stat.ast") }}</th>
                    <th>{{ _("stat.stl") }}</th>
                    <th>{{ _("stat.blk") }}</th>
                    <th>{{ _("stat.tov") }}</th>
                    <th>{{ _("stat.pf") }}</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{{ match.minutes_played if match.minutes_played is not none else "—" }}</td>
                    <td class="stat-pts">{{ match.points if match.points is not none else "—" }}</td>
                    <td>{{ computed.fg_attempts }}</td>
                    <td>{{ computed.fg_made }}</td>
                    <td>{% if computed.fg_pct is not none %}{{ "%.1f"|format(computed.fg_pct) }}%{% else %}—{% endif %}</td>
                    <td>{{ match.two_point_attempts if match.two_point_attempts is not none else "—" }}</td>
                    <td>{{ match.two_point_made if match.two_point_made is not none else "—" }}</td>
                    <td>{% if computed.two_pct is not none %}{{ "%.1f"|format(computed.two_pct) }}%{% else %}—{% endif %}</td>
                    <td>{{ match.three_point_attempts if match.three_point_attempts is not none else "—" }}</td>
                    <td>{{ match.three_point_made if match.three_point_made is not none else "—" }}</td>
                    <td>{% if computed.three_pct is not none %}{{ "%.1f"|format(computed.three_pct) }}%{% else %}—{% endif %}</td>
                    <td>{{ match.free_throw_attempts if match.free_throw_attempts is not none else "—" }}</td>
                    <td>{{ match.free_throw_made if match.free_throw_made is not none else "—" }}</td>
                    <td>{% if computed.ft_pct is not none %}{{ "%.1f"|format(computed.ft_pct) }}%{% else %}—{% endif %}</td>
                    <td>{{ match.offensive_rebounds if match.offensive_rebounds is not none else "—" }}</td>
                    <td>{{ match.defensive_rebounds if match.defensive_rebounds is not none else "—" }}</td>
                    <td>{{ match.total_rebounds if match.total_rebounds is not none else "—" }}</td>
                    <td>{{ match.assists if match.assists is not none else "—" }}</td>
                    <td>{{ match.steals if match.steals is not none else "—" }}</td>
                    <td>{{ match.blocks if match.blocks is not none else "—" }}</td>
                    <td>{{ match.turnovers if match.turnovers is not none else "—" }}</td>
                    <td>{{ match.personal_fouls if match.personal_fouls is not none else "—" }}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="advanced-stats">
        <h3 style="margin-top: 1.5rem; margin-bottom: 0.5rem;">{{ _("match.advanced_stats") }}</h3>
        <div class="advanced-stats-row">
            <div class="advanced-stat">
                <span class="advanced-stat-label">{{ _("stat.efg") }}</span>
                <span class="advanced-stat-value">{% if computed.efg_pct is not none %}{{ "%.1f"|format(computed.efg_pct) }}%{% else %}—{% endif %}</span>
            </div>
            <div class="advanced-stat">
                <span class="advanced-stat-label">{{ _("stat.ts") }}</span>
                <span class="advanced-stat-value">{% if computed.ts_pct is not none %}{{ "%.1f"|format(computed.ts_pct) }}%{% else %}—{% endif %}</span>
            </div>
        </div>
    </div>
</div>
```

---

#### Task 6.7: Update base.html nav
**File:** `app/templates/base.html` (edit)
**Depends:** none

Add a "Videos" link in the nav bar between the home link and Upload.

**Edit — Insert new line after line 13 (`<a href="/">{{ _("nav.video_bank") }}</a>`):**

```html
        <a href="/videos">{{ _("nav.videos") }}</a>
```

The nav block now reads:

```html
    <nav>
        <a href="/">{{ _("nav.video_bank") }}</a>
        <a href="/videos">{{ _("nav.videos") }}</a>
        <a href="/upload">{{ _("nav.upload") }}</a>
        <a href="/settings">{{ _("nav.settings") }}</a>
        <span id="space-indicator" style="margin-left: auto;" hx-get="/api/space" hx-trigger="load"></span>
        ...
    </nav>
```

---

#### Task 6.8: Update `_content.html` filter links
**File:** `app/templates/_content.html` (edit)
**Depends:** none

The filter bar links currently point to `/` and `/?tag_id=X`. Since the video list moved to `/videos`, these need to point to `/videos`.

**Edits:**

1. **Line 6:** Change `href="/"` → `href="/videos"`
2. **Line 7:** Change `hx-get="/"` → `hx-get="/videos"`
3. **Line 16:** Change `href="/?tag_id={{ tag.id }}"` → `href="/videos?tag_id={{ tag.id }}"`
4. **Line 17:** Change `hx-get="/?tag_id={{ tag.id }}"` → `hx-get="/videos?tag_id={{ tag.id }}"`

---

#### Task 6.9: CSS for match system
**File:** `app/static/css/style.css` (edit)
**Depends:** none

Append CSS rules for match cards, stats table, advanced stats, linked videos, and stats form.

**Edit — append to `app/static/css/style.css`:**

```css

/* ── Match Cards ────────────────────────────────────────── */
.match-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
    margin-top: 1rem;
}
.match-card {
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: box-shadow 0.2s, transform 0.2s;
}
.match-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    transform: translateY(-2px);
}
.match-card-link {
    display: block;
    padding: 1.25rem;
    text-decoration: none;
    color: inherit;
}
.match-card-title {
    font-size: 1.1rem;
    color: #4361ee;
    margin-bottom: 0.5rem;
}
.match-card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.85rem;
    color: #888;
    margin-bottom: 0.75rem;
}
.match-card-stats {
    display: flex;
    gap: 1rem;
    font-size: 0.9rem;
    color: #555;
    border-top: 1px solid #eee;
    padding-top: 0.75rem;
}
.stat-highlight {
    font-weight: 700;
    color: #e63946;
}

/* ── Stats Table ─────────────────────────────────────────── */
.stats-table-wrapper {
    overflow-x: auto;
    margin-bottom: 0.5rem;
}
.stats-table {
    border-collapse: collapse;
    font-size: 0.85rem;
    width: 100%;
    min-width: 700px;
}
.stats-table th {
    background: #1a1a2e;
    color: #fff;
    padding: 0.5rem 0.4rem;
    text-align: center;
    font-weight: 600;
    font-size: 0.75rem;
    white-space: nowrap;
}
.stats-table td {
    padding: 0.5rem 0.4rem;
    text-align: center;
    border-bottom: 1px solid #eee;
    white-space: nowrap;
}
.stats-table tbody tr:hover {
    background: #f0f4ff;
}
.stat-pts {
    font-weight: 700;
    color: #e63946;
}

/* ── Advanced Stats ──────────────────────────────────────── */
.advanced-stats-row {
    display: flex;
    gap: 2rem;
    padding: 0.75rem;
    background: #f8f9ff;
    border-radius: 8px;
}
.advanced-stat {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.advanced-stat-label {
    font-weight: 600;
    font-size: 0.9rem;
    color: #555;
}
.advanced-stat-value {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1a1a2e;
}

/* ── Linked Videos ───────────────────────────────────────── */
.linked-videos {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
.linked-video-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.linked-video-link {
    font-weight: 600;
    color: #4361ee;
    text-decoration: none;
}
.linked-video-link:hover {
    text-decoration: underline;
}
.linked-video-item .video-tags {
    margin-left: auto;
    display: flex;
    gap: 0.3rem;
}
.linked-video-item .tag-badge {
    background: #e0e7ff;
    color: #4361ee;
    padding: 0.15rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
}

/* ── Stats Form Grid ─────────────────────────────────────── */
.stats-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.75rem;
}
.stat-field label {
    font-size: 0.8rem;
    color: #888;
    margin-bottom: 0.15rem;
}
.stat-field input {
    width: 100%;
    padding: 0.4rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 0.9rem;
}

/* ── Match Videos Section (Link/Remove controls) ─────────── */
.match-video-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: auto;
}
.link-video-form {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1rem;
    padding: 0.75rem;
    background: #f8f9ff;
    border-radius: 8px;
}
.link-video-form select {
    padding: 0.4rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
    flex: 1;
}

/* ── Match Context on Video Detail ───────────────────────── */
.match-context {
    margin-bottom: 1.5rem;
    padding: 0.75rem;
    background: #f0f4ff;
    border-radius: 8px;
}
.match-context h3 {
    font-size: 0.9rem;
    color: #888;
    margin-bottom: 0.5rem;
}
.match-context-item {
    display: inline-block;
    margin-right: 0.75rem;
    margin-bottom: 0.25rem;
    padding: 0.25rem 0.75rem;
    background: #fff;
    border-radius: 4px;
    font-size: 0.85rem;
    color: #4361ee;
    text-decoration: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.match-context-item:hover {
    background: #e0e7ff;
}

/* ── Responsive: Match Cards ─────────────────────────────── */
@media (max-width: 768px) {
    .match-grid {
        grid-template-columns: 1fr;
    }
    .stats-form-grid {
        grid-template-columns: repeat(2, 1fr);
    }
    .advanced-stats-row {
        flex-direction: column;
        gap: 0.75rem;
    }
}
```

---

## Checkpoint 2 STOP — Validate with user

Navigate to `/` (should show matches), `/videos` (should show video grid), `/matches/new` (form renders), click through to match detail.

---

## Checkpoint 3: Video-Match Linking UI

### Batch 7: Interactive UI Enhancements (parallel — 3 implementers)

#### Task 7.1: `_match_videos.html` with Link/Remove UI
**File:** `app/templates/_match_videos.html` (replace)
**Depends:** 6.5 (existing basic version)

Replace the basic file with an HTMX-enabled version that has link/remove controls.

**Complete replacement — `app/templates/_match_videos.html`:**

```html
{% if match.videos and match.videos|length > 0 %}
<div class="linked-videos">
    {% for video in match.videos %}
    <div class="linked-video-item">
        <a href="/videos/{{ video.id }}" class="linked-video-link">{{ video.name }}</a>
        {% if video.tags and video.tags|length > 0 %}
        <div class="video-tags">
            {% for tag in video.tags %}
            <span class="tag-badge">{{ tag }}</span>
            {% endfor %}
        </div>
        {% endif %}
        <div class="match-video-controls">
            <button class="btn btn-danger btn-sm"
                    hx-post="/api/matches/{{ match.id }}/videos/{{ video.id }}/remove"
                    hx-target="#match-videos-section"
                    hx-swap="outerHTML">
                {{ _("match.remove_video") }}
            </button>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<p style="color: #888;">{{ _("match.no_videos") }}</p>
{% endif %}

{% if unlinked_videos and unlinked_videos|length > 0 %}
<form class="link-video-form"
      hx-post="/api/matches/{{ match.id }}/videos"
      hx-target="#match-videos-section"
      hx-swap="outerHTML">
    <select name="video_id">
        {% for v in unlinked_videos %}
        <option value="{{ v.id }}">{{ v.name }}</option>
        {% endfor %}
    </select>
    <button type="submit" class="btn btn-primary btn-sm">{{ _("match.link_video") }}</button>
</form>
{% endif %}
```

---

#### Task 7.2: Update video_detail.html with match context
**File:** `app/templates/video_detail.html` (edit)
**Depends:** none (but requires match_service.get_video_matches to be called from route)

Add a "Part of match" section between the page title and the video player. This requires the route to pass a `matches` list (video's linked matches).

**Also need route edit:** In `app/routes/videos.py`, modify `video_detail` (line ~224) to also fetch matches for the video:

```python
@router.get("/videos/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db)):
    i18n = get_i18n(request)
    video = await video_service.get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    enriched["video_url"] = f"/api/videos/{video_id}/file"

    # Get matches this video belongs to
    from app.services.match_service import get_video_matches
    video_matches = await get_video_matches(db, video_id)

    return templates.TemplateResponse(
        request,
        "video_detail.html",
        {
            **i18n,
            "video": enriched,
            "video_matches": video_matches,
        },
    )
```

**Template edit — `app/templates/video_detail.html`:**

After line 18 (`</div>` closing the page-header), insert:

```html
    {% if video_matches and video_matches|length > 0 %}
    <div class="match-context">
        <h3>{{ _("match.linked_matches") }}</h3>
        {% for m in video_matches %}
        <a href="/matches/{{ m.id }}" class="match-context-item">
            {{ m.name }} ({{ m.match_date }})
        </a>
        {% endfor %}
    </div>
    {% endif %}
```

And change line 8 (the back link) from:
```html
<a href="/" style="...">{{ _("link.back_to_videos") }}</a>
```
to:
```html
<a href="/videos" style="...">{{ _("link.back_to_videos") }}</a>
```

---

#### Task 7.3: Add linking UI tests
**File:** `tests/test_matches.py` (edit — add to existing file)
**Depends:** 7.1, 7.2

Append additional test classes for the video linking UI interactive features.

**Edit — append to `tests/test_matches.py`:**

```python

class TestMatchLinkingUI:
    """Tests for video linking interactive UI (Checkpoint 3)."""

    @pytest.mark.asyncio
    async def test_link_video_htmx_fragment(self, client):
        """POST /api/matches/{id}/videos returns HTML fragment with linked videos."""
        video_id = await create_test_video(client, "HTMX Link", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "HTMX Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        response = await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should be a fragment (no full page wrapper)
        assert "HTMX Link" in response.text

    @pytest.mark.asyncio
    async def test_unlink_video_htmx_fragment(self, client):
        """POST /api/matches/{id}/videos/{vid}/remove returns HTML fragment."""
        video_id = await create_test_video(client, "Unlink Me", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Unlink Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link first
        await client.post(f"/api/matches/{match_id}/videos", data={"video_id": str(video_id)})

        # Unlink via HTMX
        response = await client.post(
            f"/api/matches/{match_id}/videos/{video_id}/remove",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "Unlink Me" not in response.text
        # Should show empty state message (i18n: "No videos linked")
        assert "videos linked" in response.text.lower() or "aucune" in response.text.lower()

    @pytest.mark.asyncio
    async def test_match_detail_shows_unlinked_videos_in_picker(self, client):
        """Match detail page includes unlinked videos for the picker."""
        video_id = await create_test_video(client, "Picker Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Picker Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 200
        # Should show the video in the link picker
        assert "Picker Video" in detail.text

    @pytest.mark.asyncio
    async def test_video_detail_shows_match_context(self, client):
        """Video detail page shows matches the video belongs to."""
        video_id = await create_test_video(client, "Linked Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Context Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link video to match
        await client.post(f"/api/matches/{match_id}/videos", data={"video_id": str(video_id)})

        # Video detail should show match context
        detail = await client.get(f"/videos/{video_id}")
        assert detail.status_code == 200
        assert "Context Match" in detail.text

    @pytest.mark.asyncio
    async def test_video_detail_back_link_goes_to_videos(self, client):
        """Video detail back link points to /videos, not /."""
        video_id = await create_test_video(client, "Back Link", "")
        detail = await client.get(f"/videos/{video_id}")
        assert 'href="/videos"' in detail.text or 'href="/videos' in detail.text
```

---

## Checkpoint 3 STOP — Validate with user

Full integration test: create match → link video → verify on both match detail and video detail → unlink → verify removed.

---

## Dependency Graph Summary

```
CP1: Database + Backend
├── Batch 1 (parallel — 3 tasks):  1.1 database.py │ 1.2 stats_calculator.py │ 1.3 videos.py (route swap)
├── Batch 2 (parallel — 2 tasks):  2.1 match_service.py │ 2.2 conftest.py
├── Batch 3 (parallel — 2 tasks):  3.1 routes/matches.py │ 3.2 main.py
└── Batch 4 (1 task):              4.1 tests/test_matches.py (backend)
    → STOP — validate

CP2: Frontend
├── Batch 5 (parallel — 2 tasks):  5.1 en.json │ 5.2 fr.json
└── Batch 6 (parallel — 9 tasks):  6.1-6.9 all templates + CSS
    → STOP — validate

CP3: Video-Match Linking UI
├── Batch 7 (parallel — 3 tasks):  7.1 _match_videos.html │ 7.2 video_detail.html (+ route edit) │ 7.3 tests
    → STOP — validate
```

Total: **19 micro-tasks** across **7 batches** in **3 checkpoints**.

## Verification Commands

After each batch completes, run:
```bash
# Quick syntax check on Python files
python -c "import py_compile; py_compile.compile('app/database.py', doraise=True)"
python -c "import py_compile; py_compile.compile('app/services/stats_calculator.py', doraise=True)"

# Run all backend tests
python -m pytest tests/test_matches.py -v

# Ensure no regression on existing tests
python -m pytest tests/test_videos.py -v tests/test_tags.py -v
```
