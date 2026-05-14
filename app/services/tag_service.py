"""
Tag management: create, list, associate with videos.
"""


async def get_or_create_tag(db, name: str) -> int:
    """Find a tag by name or create it. Returns the tag id."""
    name = name.strip().lower()
    if not name:
        raise ValueError("Tag name cannot be empty")

    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row:
        return row["id"]

    cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    await db.commit()
    return cursor.lastrowid


async def list_all_tags(db) -> list[dict]:
    """Return all tags, ordered by name."""
    cursor = await db.execute("SELECT * FROM tags ORDER BY name ASC")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_video_tags(db, video_id: int) -> list[str]:
    """Return tag names for a given video."""
    cursor = await db.execute(
        """SELECT t.name FROM tags t
           JOIN video_tags vt ON t.id = vt.tag_id
           WHERE vt.video_id = ?
           ORDER BY t.name""",
        (video_id,),
    )
    rows = await cursor.fetchall()
    return [r["name"] for r in rows]


async def set_video_tags(db, video_id: int, tag_names: list[str]):
    """Replace all tags on a video with the given list.

    Tags that don't exist yet are created on the fly.
    """
    # Remove existing associations
    await db.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))

    # Add new ones
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag_id = await get_or_create_tag(db, name)
        await db.execute(
            "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
            (video_id, tag_id),
        )

    await db.commit()
