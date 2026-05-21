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
    account_id: int | None = None,
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

    columns = ", ".join(["name", "match_date", "opponent", "location", "notes", "account_id"] + stat_fields)
    placeholders = ", ".join(["?"] * (6 + len(stat_fields)))
    values = [name.strip(), match_date.strip(), opponent, location, notes, account_id] + stat_values

    cursor = await db.execute(
        f"INSERT INTO matches ({columns}) VALUES ({placeholders})",
        values,
    )
    await db.commit()
    match_id = cursor.lastrowid
    logger.info("Match created: id=%d, name=%s", match_id, name)
    return await get_match(db, match_id, account_id=account_id)


async def get_match(db: aiosqlite.Connection, match_id: int, account_id: int | None = None) -> dict | None:
    """Fetch a single match by ID. Returns None if not found."""
    if account_id is None:
        cursor = await db.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    else:
        cursor = await db.execute(
            "SELECT * FROM matches WHERE id = ? AND account_id = ?",
            (match_id, account_id),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_matches(db: aiosqlite.Connection, account_id: int | None = None) -> list[dict]:
    """Return all matches ordered by match_date descending."""
    if account_id is None:
        cursor = await db.execute("SELECT * FROM matches ORDER BY match_date DESC")
    else:
        cursor = await db.execute(
            "SELECT * FROM matches WHERE account_id = ? ORDER BY match_date DESC",
            (account_id,),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_match(
    db: aiosqlite.Connection,
    match_id: int,
    account_id: int | None = None,
    **fields,
) -> dict | None:
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
        return await get_match(db, match_id, account_id=account_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [match_id]

    if account_id is None:
        cursor = await db.execute(
            f"UPDATE matches SET {set_clause} WHERE id = ?",
            values,
        )
    else:
        values.append(account_id)
        cursor = await db.execute(
            f"UPDATE matches SET {set_clause} WHERE id = ? AND account_id = ?",
            values,
        )
    await db.commit()
    if cursor.rowcount == 0:
        return None
    logger.info("Match updated: id=%d, fields=%s", match_id, list(updates.keys()))
    return await get_match(db, match_id, account_id=account_id)


async def delete_match(db: aiosqlite.Connection, match_id: int, account_id: int | None = None) -> bool:
    """Delete a match. Returns True if deleted, False if not found.

    ON DELETE CASCADE cleans up match_videos associations automatically.
    """
    if account_id is None:
        cursor = await db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    else:
        cursor = await db.execute(
            "DELETE FROM matches WHERE id = ? AND account_id = ?",
            (match_id, account_id),
        )
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Match deleted: id=%d", match_id)
    return deleted


async def link_video(
    db: aiosqlite.Connection,
    match_id: int,
    video_id: int,
    account_id: int | None = None,
) -> bool:
    """Link an account-owned video to an account-owned match."""
    if account_id is not None:
        if await get_match(db, match_id, account_id=account_id) is None:
            return False
        cursor = await db.execute(
            "SELECT id FROM videos WHERE id = ? AND account_id = ?",
            (video_id, account_id),
        )
        if await cursor.fetchone() is None:
            return False
    await db.execute(
        "INSERT OR IGNORE INTO match_videos (match_id, video_id) VALUES (?, ?)",
        (match_id, video_id),
    )
    await db.commit()
    return True


async def unlink_video(
    db: aiosqlite.Connection,
    match_id: int,
    video_id: int,
    account_id: int | None = None,
) -> bool:
    """Remove an account-owned video from an account-owned match."""
    if account_id is None:
        cursor = await db.execute(
            "DELETE FROM match_videos WHERE match_id = ? AND video_id = ?",
            (match_id, video_id),
        )
    else:
        cursor = await db.execute(
            """DELETE FROM match_videos
               WHERE match_id = ?
                 AND video_id = ?
                 AND EXISTS (SELECT 1 FROM matches m WHERE m.id = match_videos.match_id AND m.account_id = ?)
                 AND EXISTS (SELECT 1 FROM videos v WHERE v.id = match_videos.video_id AND v.account_id = ?)""",
            (match_id, video_id, account_id, account_id),
        )
    await db.commit()
    return cursor.rowcount > 0


async def get_match_with_videos(
    db: aiosqlite.Connection,
    match_id: int,
    account_id: int | None = None,
) -> dict | None:
    """Fetch a match along with its linked videos (each with tags)."""
    match = await get_match(db, match_id, account_id=account_id)
    if match is None:
        return None

    if account_id is None:
        cursor = await db.execute(
            """SELECT v.* FROM videos v
               JOIN match_videos mv ON v.id = mv.video_id
               WHERE mv.match_id = ?
               ORDER BY v.upload_date DESC""",
            (match_id,),
        )
    else:
        cursor = await db.execute(
            """SELECT v.* FROM videos v
               JOIN match_videos mv ON v.id = mv.video_id
               WHERE mv.match_id = ? AND v.account_id = ?
               ORDER BY v.upload_date DESC""",
            (match_id, account_id),
        )
    videos = [dict(r) for r in await cursor.fetchall()]

    # Attach tags to each video
    from app.services.tag_service import get_video_tags
    for v in videos:
        v["tags"] = await get_video_tags(db, v["id"], account_id=account_id)

    match["videos"] = videos
    return match


async def get_match_with_stats(
    db: aiosqlite.Connection,
    match_id: int,
    account_id: int | None = None,
) -> dict | None:
    """Fetch a match with computed statistics.

    Returns dict with 'match' (raw) and 'computed' (derived stats).
    Returns None if match not found.
    """
    match = await get_match(db, match_id, account_id=account_id)
    if match is None:
        return None
    return {
        "match": match,
        "computed": compute_all(match),
    }


async def get_unlinked_videos(
    db: aiosqlite.Connection,
    match_id: int,
    account_id: int | None = None,
) -> list[dict]:
    """Return videos NOT already linked to this match.

    Used for the 'Link Video' picker UI.
    """
    if account_id is not None and await get_match(db, match_id, account_id=account_id) is None:
        return []

    if account_id is None:
        cursor = await db.execute(
            """SELECT v.id, v.name, v.filename, v.mime_type
               FROM videos v
               WHERE v.id NOT IN (
                   SELECT video_id FROM match_videos WHERE match_id = ?
               )
               ORDER BY v.upload_date DESC""",
            (match_id,),
        )
    else:
        cursor = await db.execute(
            """SELECT v.id, v.name, v.filename, v.mime_type
               FROM videos v
               WHERE v.account_id = ?
                 AND v.id NOT IN (
                     SELECT video_id FROM match_videos WHERE match_id = ?
                 )
               ORDER BY v.upload_date DESC""",
            (account_id, match_id),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_video_matches(
    db: aiosqlite.Connection,
    video_id: int,
    account_id: int | None = None,
) -> list[dict]:
    """Return all matches that a video is linked to."""
    if account_id is None:
        cursor = await db.execute(
            """SELECT m.id, m.name, m.match_date
               FROM matches m
               JOIN match_videos mv ON m.id = mv.match_id
               WHERE mv.video_id = ?
               ORDER BY m.match_date DESC""",
            (video_id,),
        )
    else:
        cursor = await db.execute(
            """SELECT m.id, m.name, m.match_date
               FROM matches m
               JOIN match_videos mv ON m.id = mv.match_id
               JOIN videos v ON v.id = mv.video_id
               WHERE mv.video_id = ? AND m.account_id = ? AND v.account_id = ?
               ORDER BY m.match_date DESC""",
            (video_id, account_id, account_id),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def compute_year_summary(db: aiosqlite.Connection, account_id: int | None = None) -> list[dict]:
    """Compute per-year and overall stat averages from all matches.

    Returns a list of row dicts suitable for the summary table, one per
    year (oldest first) plus a final row for all years combined.

    Each row contains:
      - label (str): year string or "All" for the overall row
      - match_count (int): number of games in that group
      - Per-game averages for every raw stat field (float, 1 decimal)
      - fg_attempts, fg_made: per-game averages (float, 1 decimal)
      - fg_pct, two_pct, three_pct, ft_pct, efg_pct, ts_pct:
        season percentages computed from aggregate totals (float or None)

    Returns an empty list if there are no matches.
    """
    if account_id is None:
        cursor = await db.execute("SELECT * FROM matches ORDER BY match_date ASC")
    else:
        cursor = await db.execute(
            "SELECT * FROM matches WHERE account_id = ? ORDER BY match_date ASC",
            (account_id,),
        )
    matches = [dict(r) for r in await cursor.fetchall()]

    if not matches:
        return []

    # Group by year
    from collections import defaultdict

    years: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        year = m["match_date"][:4] if m.get("match_date") else "?"
        years[year].append(m)

    raw_fields = [
        "minutes_played", "points",
        "two_point_attempts", "two_point_made",
        "three_point_attempts", "three_point_made",
        "free_throw_attempts", "free_throw_made",
        "offensive_rebounds", "defensive_rebounds", "total_rebounds",
        "assists", "steals", "blocks", "turnovers", "personal_fouls",
    ]

    from app.services.stats_calculator import compute_all

    def _row(label: str, group: list[dict]) -> dict:
        count = len(group)
        # Sum raw stats
        sums = {f: 0.0 for f in raw_fields}
        for m in group:
            for f in raw_fields:
                v = m.get(f)
                if v is not None:
                    sums[f] += v
        # Per-game averages for raw stats
        row: dict = {"label": label, "match_count": count}
        for f in raw_fields:
            row[f] = round(sums[f] / count, 1) if count else 0
        # Computed stats from aggregate totals
        computed = compute_all({k: int(v) for k, v in sums.items()})
        # Per-game averages for FGA / FGM (compute_all returns total counts)
        row["fg_attempts"] = round(computed["fg_attempts"] / count, 1) if count else 0
        row["fg_made"] = round(computed["fg_made"] / count, 1) if count else 0
        # Percentages stay as computed from aggregate totals
        for k in ("fg_pct", "two_pct", "three_pct", "ft_pct", "efg_pct", "ts_pct"):
            row[k] = computed.get(k)
        return row

    rows = []
    for year in sorted(years.keys()):
        rows.append(_row(year, years[year]))
    rows.append(_row("All", matches))
    return rows
