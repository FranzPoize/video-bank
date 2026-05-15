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


async def get_tag(db, tag_id: int) -> dict | None:
    """Fetch a single tag by id. Returns None if not found."""
    cursor = await db.execute("SELECT id, name FROM tags WHERE id = ?", (tag_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def update_tag(db, tag_id: int, new_name: str) -> dict:
    """Rename a tag. Returns updated tag dict or raises ValueError on duplicate/empty."""
    new_name = new_name.strip().lower()
    if not new_name:
        raise ValueError("Tag name cannot be empty")

    # Check if new name already exists for a different tag
    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (new_name,))
    existing = await cursor.fetchone()
    if existing and existing["id"] != tag_id:
        raise ValueError("A tag with this name already exists")

    # Update the tag
    await db.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
    await db.commit()

    # Return updated tag
    updated = await get_tag(db, tag_id)
    if not updated:
        raise ValueError("Tag not found")
    return updated


async def delete_tag(db, tag_id: int) -> bool:
    """Delete a tag. Returns True if deleted, False if not found.

    ON DELETE CASCADE in schema handles video_tags cleanup automatically.
    """
    cursor = await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    await db.commit()
    return cursor.rowcount > 0


async def list_all_tags_with_counts(db) -> list[dict]:
    """List all tags with video usage counts. Ordered by name."""
    cursor = await db.execute("""
        SELECT t.id, t.name, COUNT(vt.video_id) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON t.id = vt.tag_id
        GROUP BY t.id
        ORDER BY t.name
    """)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
