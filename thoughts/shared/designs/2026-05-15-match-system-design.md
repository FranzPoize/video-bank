---
date: 2026-05-15
topic: "Match System for Video Bank"
status: validated
---

## Problem Statement

The Video Bank currently manages videos in a flat grid — upload, tag, clip, view. There's no way to group videos by real-world events like basketball matches. Users need to organize videos by match, track box score statistics alongside those matches, and navigate between matches and their associated videos.

## Constraints

- **No ORM** — raw SQL via aiosqlite, consistent with existing codebase
- **No frontend framework** — server-rendered Jinja2 + HTMX + vanilla JS
- **Single-file SQLite** — no separate database server
- **Existing migration system** — versioned SQL statements in `database.py`, new migration v5
- **Existing test patterns** — in-memory SQLite, httpx AsyncClient, service functions take `db` as first arg
- **i18n** — all new UI strings need translation entries (English + French)

## Approach

Flat schema design: all box score stats live as nullable columns directly on the `matches` table. This avoids over-engineering (stats are one-to-one with matches) and keeps queries simple. Calculated stats are derived via a pure Python utility module, not stored.

Three incremental checkpoints:
1. **Database + Backend** — schema, service, routes, stats calculator, all tests
2. **Frontend** — match list/detail/form templates, nav restructure, `/videos` route
3. **Video linking** — UI for associating videos with matches, match context on video page

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI App                            │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ matches.py   │  │ videos.py    │  │ tags.py          │ │
│  │ (routes)     │  │ (routes)     │  │ (routes)         │ │
│  └──────┬───────┘  └──────┬───────┘  └─────────────────┘ │
│         │                 │                               │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌─────────────────┐ │
│  │ match_svc    │  │ video_svc    │  │ tag_svc         │ │
│  │ (service)    │  │ (service)    │  │ (service)        │ │
│  └──────┬───────┘  └──────────────┘  └─────────────────┘ │
│         │                                                 │
│  ┌──────▼───────┐                                         │
│  │ stats_calc   │  (pure functions, no DB)                │
│  └──────────────┘                                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │           SQLite (database.py v5)                │    │
│  │  matches │ match_videos │ videos │ tags │ ...    │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**Key structural decision:** The `/` route moves from showing videos to showing matches. Videos get their own route at `/videos`. This is the only breaking change to existing navigation.

## Components

### 1. Match Service (`app/services/match_service.py`)

Follows the exact same pattern as `video_service.py`:

- `create_match(db, name, match_date, **stats)` — INSERT into matches, return created match
- `get_match(db, match_id)` — SELECT by id, return dict or None
- `get_match_with_videos(db, match_id)` — match + list of linked videos with tags
- `get_match_with_stats(db, match_id)` — match raw stats + computed stats (calls stats_calculator)
- `list_matches(db)` — SELECT all ordered by match_date DESC
- `update_match(db, match_id, **fields)` — UPDATE specified fields
- `delete_match(db, match_id)` — DELETE (ON DELETE CASCADE cleans up match_videos)
- `link_video(db, match_id, video_id)` — INSERT into match_videos
- `unlink_video(db, match_id, video_id)` — DELETE from match_videos
- `get_unlinked_videos(db, match_id)` — videos NOT already linked to this match (for "add video" UI)

### 2. Stats Calculator (`app/services/stats_calculator.py`)

Pure functions, zero dependencies:

- `compute_all(raw: dict) -> dict` — takes raw stats dict, returns enriched dict with computed fields:
  - `fg_attempts` = `2pa + 3pa`
  - `fg_made` = `2pm + 3pm`
  - `two_pct` = `2pm / 2pa` (0 if 2pa=0)
  - `three_pct` = `3pm / 3pa` (0 if 3pa=0)
  - `ft_pct` = `ftm / fta` (0 if fta=0)
  - `efg_pct` = `(fgm + 0.5 * 3pm) / fga` (0 if fga=0)
  - `ts_pct` = `pts / (2 * fga + 0.44 * fta)` (0 if denominator=0)

Field name mapping (DB snake_case → display):
- `minutes_played` → MP
- `points` → PTS
- `two_point_attempts` → 2PA
- etc. — templates handle the display names via i18n

### 3. Match Routes (`app/routes/matches.py`)

New router, registered in `main.py` alongside videos and tags:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Match list (becomes home page) |
| `GET` | `/matches/new` | Create match form |
| `POST` | `/api/matches` | Create match |
| `GET` | `/matches/{id}` | Match detail (stats + videos) |
| `GET` | `/matches/{id}/edit` | Edit match form |
| `POST` | `/api/matches/{id}` | Update match |
| `POST` | `/matches/{id}/delete` | Delete match |
| `POST` | `/api/matches/{id}/videos` | Link video to match |
| `POST` | `/api/matches/{id}/videos/{vid}/remove` | Remove video from match |

The existing `/` handler in `videos.py` is replaced with a redirect to `/videos` or removed in favor of the matches router's `/` handler. Need to ensure only one `/` route exists — the matches router takes precedence.

### 4. Templates

- **`match_list.html`** — new home page, shows match cards in a grid/list
- **`match_detail.html`** — match header + stats table (raw + calculated) + linked videos section
- **`match_form.html`** — shared create/edit form with all stat fields
- **`_match_card.html`** — HTMX fragment for individual match card in list
- **`_match_videos.html`** — HTMX fragment showing videos linked to a match
- **`_match_stats.html`** — HTMX fragment for the stats table
- **`video_detail.html`** — updated to show which match(s) the video belongs to
- **`base.html`** — nav updated with "Videos" link

### 5. Nav Structure (Updated)

```
[Video Bank]  [Videos]  [Upload]  [Settings]  [🇬🇧 EN ▼]
     ↓            ↓
  matches      old home
  (home)       page content
```

## Data Flow

### Match Creation
```
Form submit → POST /api/matches → match_service.create_match()
  → validate required fields (name, date)
  → INSERT INTO matches
  → redirect to /matches/{id}
```

### Match Detail with Stats
```
GET /matches/{id} → match_service.get_match_with_videos(id)
  → SELECT FROM matches WHERE id=?
  → SELECT videos + tags via match_videos JOIN
  → stats_calculator.compute_all(raw_stats)
  → render match_detail.html with stats + videos
```

### Linking Video to Match
```
Match detail page → user clicks "Link Video" → picks from unlinked videos
  → POST /api/matches/{id}/videos {video_id}
  → INSERT INTO match_videos (match_id, video_id)
  → HTMX re-renders _match_videos.html fragment
```

### Home Page
```
GET / → match_service.list_matches()
  → SELECT id, name, match_date, points, ... FROM matches ORDER BY match_date DESC
  → render match_list.html with match cards showing compact stats
```

## Database Schema (Migration v5)

```sql
CREATE TABLE matches (
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

CREATE INDEX idx_matches_date ON matches(match_date DESC);

CREATE TABLE match_videos (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    UNIQUE(match_id, video_id)
);

CREATE INDEX idx_match_videos_match ON match_videos(match_id);
CREATE INDEX idx_match_videos_video ON match_videos(video_id);
```

## Error Handling

| Scenario | Response |
|----------|----------|
| Match not found | 404 page (existing `error.html` template) |
| Invalid stats values (negative) | Server-side validation, 400 with inline error message |
| Division by zero in stats | Calculator returns 0.0 or `"—"` for the cell |
| Duplicate video link | UNIQUE constraint — catch IntegrityError, return friendly message |
| Delete match with linked videos | CASCADE — works automatically, videos survive |
| Missing required fields (name, date) | Form validation, 400 with error message |

## Testing Strategy

**Test file:** `tests/test_matches.py` (~150-200 lines)

| Test area | Tests |
|-----------|-------|
| Match creation | Valid match creates DB record, missing name/date raises error |
| Match listing | Empty list, multiple matches ordered by date desc |
| Match detail | Returns match + stats, 404 for unknown ID |
| Match update | Updates name, date, individual stats |
| Match delete | Deletes match, cascade removes associations |
| Stats calculator | All 7 formulas, zero-division edge cases, missing stats (None) |
| Link video | Links to match, duplicate link rejected |
| Unlink video | Removes association, other videos unaffected |
| Home page shows matches | GET `/` returns match content not video grid |
| Videos page | GET `/videos` returns video grid (old behavior preserved) |

All tests use existing `conftest.py` fixtures: in-memory `db`, httpx `client` with DB dependency override, `create_test_video` helper.

## Open Questions

- Should `total_rebounds` be stored or always calculated as ORB + DRB? **Decision: store it.** Many box scores include TRB as a stat-line item. If it's missing, the UI can still display ORB+DRB derived value.
- Should a video be linkable to multiple matches? **Yes** — the join table allows this naturally.
- Minutes played: stored as REAL for fractional minutes (e.g. 32.5 = 32:30). The display template formats this as needed.

## Checkpoints

### Checkpoint 1: Database + Backend
- Database migration v5 (matches + match_votes tables)
- `app/services/stats_calculator.py` (pure computed stats)
- `app/services/match_service.py` (match CRUD + video linking)
- `app/routes/matches.py` (all match endpoints)
- `/` handler swapped to match list, `/videos` handler added
- `match_service` registered in `main.py`
- All backend tests pass
- **STOP — validate with user**

### Checkpoint 2: Frontend
- Templates: match_list, match_detail, match_form, _match_card, _match_videos, _match_stats
- Nav updated in base.html (add "Videos" link)
- `/videos` rendered correctly (old behavior preserved)
- i18n translations for all new strings (en.json + fr.json)
- CSS for stat tables and match cards
- **STOP — validate with user**

### Checkpoint 3: Video-Match Linking UI
- "Link Video" UI on match detail page (select from unlinked videos)
- "Remove" button on linked videos
- Match context shown on video detail page
- HTMX fragments for dynamic add/remove without full page reload
- **STOP — validate with user**
