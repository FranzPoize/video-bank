"""
Tag management: create, list, associate with videos.
"""

import aiosqlite


async def get_or_create_tag(
    db: aiosqlite.Connection,
    name: str,
    account_id: int | None = None,
) -> int:
    """Find a tag by name/account or create it. Returns the tag id."""
    name = name.strip().lower()
    if not name:
        raise ValueError("Tag name cannot be empty")

    if account_id is None:
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND account_id IS NULL",
            (name,),
        )
    else:
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND account_id = ?",
            (name, account_id),
        )
    row = await cursor.fetchone()
    if row:
        return row["id"]

    cursor = await db.execute(
        "INSERT INTO tags (name, account_id) VALUES (?, ?)",
        (name, account_id),
    )
    await db.commit()
    return cursor.lastrowid


async def list_all_tags(
    db: aiosqlite.Connection,
    account_id: int | None = None,
) -> list[dict]:
    """Return all tags for an account, ordered by name."""
    if account_id is None:
        cursor = await db.execute(
            "SELECT * FROM tags WHERE account_id IS NULL ORDER BY name ASC"
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM tags WHERE account_id = ? ORDER BY name ASC",
            (account_id,),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_video_tags(
    db: aiosqlite.Connection,
    video_id: int,
    account_id: int | None = None,
) -> list[str]:
    """Return tag names for a video in an account."""
    if account_id is None:
        cursor = await db.execute(
            """SELECT t.name FROM tags t
               JOIN video_tags vt ON t.id = vt.tag_id
               JOIN videos v ON v.id = vt.video_id
               WHERE vt.video_id = ?
                 AND v.account_id IS NULL
                 AND t.account_id IS NULL
               ORDER BY t.name""",
            (video_id,),
        )
    else:
        cursor = await db.execute(
            """SELECT t.name FROM tags t
               JOIN video_tags vt ON t.id = vt.tag_id
               JOIN videos v ON v.id = vt.video_id
               WHERE vt.video_id = ?
                 AND v.account_id = ?
                 AND t.account_id = ?
               ORDER BY t.name""",
            (video_id, account_id, account_id),
        )
    rows = await cursor.fetchall()
    return [r["name"] for r in rows]


async def set_video_tags(
    db: aiosqlite.Connection,
    video_id: int,
    tag_names: list[str],
    account_id: int | None = None,
):
    """Replace all tags on an account-owned video with the given list.

    Tags that don't exist yet are created on the fly.
    """
    if account_id is None:
        cursor = await db.execute(
            "SELECT id FROM videos WHERE id = ? AND account_id IS NULL",
            (video_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT id FROM videos WHERE id = ? AND account_id = ?",
            (video_id, account_id),
        )
    if await cursor.fetchone() is None:
        raise ValueError("Video not found")

    await db.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))

    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag_id = await get_or_create_tag(db, name, account_id=account_id)
        await db.execute(
            "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
            (video_id, tag_id),
        )

    await db.commit()


async def get_tag(
    db: aiosqlite.Connection,
    tag_id: int,
    account_id: int | None = None,
) -> dict | None:
    """Fetch a single account tag by id. Returns None if not found."""
    if account_id is None:
        cursor = await db.execute(
            "SELECT id, name, account_id FROM tags WHERE id = ? AND account_id IS NULL",
            (tag_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT id, name, account_id FROM tags WHERE id = ? AND account_id = ?",
            (tag_id, account_id),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def update_tag(
    db: aiosqlite.Connection,
    tag_id: int,
    new_name: str,
    account_id: int | None = None,
) -> dict:
    """Rename an account tag. Returns updated tag dict or raises ValueError."""
    new_name = new_name.strip().lower()
    if not new_name:
        raise ValueError("Tag name cannot be empty")

    current = await get_tag(db, tag_id, account_id=account_id)
    if not current:
        raise ValueError("Tag not found")

    if account_id is None:
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND account_id IS NULL",
            (new_name,),
        )
    else:
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND account_id = ?",
            (new_name, account_id),
        )
    existing = await cursor.fetchone()
    if existing and existing["id"] != tag_id:
        raise ValueError("A tag with this name already exists")

    if account_id is None:
        await db.execute(
            "UPDATE tags SET name = ? WHERE id = ? AND account_id IS NULL",
            (new_name, tag_id),
        )
    else:
        await db.execute(
            "UPDATE tags SET name = ? WHERE id = ? AND account_id = ?",
            (new_name, tag_id, account_id),
        )
    await db.commit()

    updated = await get_tag(db, tag_id, account_id=account_id)
    if not updated:
        raise ValueError("Tag not found")
    return updated


async def delete_tag(
    db: aiosqlite.Connection,
    tag_id: int,
    account_id: int | None = None,
) -> bool:
    """Delete an account tag. Returns True if deleted, False if not found.

    ON DELETE CASCADE in schema handles video_tags cleanup automatically.
    """
    if account_id is None:
        cursor = await db.execute(
            "DELETE FROM tags WHERE id = ? AND account_id IS NULL",
            (tag_id,),
        )
    else:
        cursor = await db.execute(
            "DELETE FROM tags WHERE id = ? AND account_id = ?",
            (tag_id, account_id),
        )
    await db.commit()
    return cursor.rowcount > 0


async def list_all_tags_with_counts(
    db: aiosqlite.Connection,
    account_id: int | None = None,
) -> list[dict]:
    """List account tags with video usage counts. Ordered by name."""
    if account_id is None:
        cursor = await db.execute("""
            SELECT t.id, t.name, t.account_id, COUNT(v.id) as video_count
            FROM tags t
            LEFT JOIN video_tags vt ON t.id = vt.tag_id
            LEFT JOIN videos v ON v.id = vt.video_id AND v.account_id IS NULL
            WHERE t.account_id IS NULL
            GROUP BY t.id
            ORDER BY t.name
        """)
    else:
        cursor = await db.execute("""
            SELECT t.id, t.name, t.account_id, COUNT(v.id) as video_count
            FROM tags t
            LEFT JOIN video_tags vt ON t.id = vt.tag_id
            LEFT JOIN videos v ON v.id = vt.video_id AND v.account_id = ?
            WHERE t.account_id = ?
            GROUP BY t.id
            ORDER BY t.name
        """, (account_id, account_id))
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
