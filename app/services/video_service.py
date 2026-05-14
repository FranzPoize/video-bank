"""
Business logic for video CRUD operations.

Each function takes an aiosqlite.Connection as the first argument.
This keeps them testable with in-memory databases.
"""

from app.database import get_db
from app.services import file_service


async def create_video(
    db,
    name: str,
    file_content: bytes,
    original_name: str,
    mime_type: str,
    file_size: int,
) -> dict:
    """Save a video file and create a database record.
    
    Returns the created video as a dict.
    """
    # Validate file before saving
    error = file_service.validate_file(original_name, file_size)
    if error:
        raise ValueError(error)

    # Save file to disk
    filename = await file_service.save_upload(file_content, original_name)

    # Generate thumbnail (best-effort — placeholder in CP1, ffmpeg in CP2)
    await file_service.generate_thumbnail(filename)

    # Insert database record
    cursor = await db.execute(
        """INSERT INTO videos (name, filename, original_name, mime_type, file_size)
           VALUES (?, ?, ?, ?, ?)""",
        (name, filename, original_name, mime_type, file_size),
    )
    await db.commit()
    video_id = cursor.lastrowid

    return await get_video(db, video_id)


async def get_video(db, video_id: int) -> dict | None:
    """Fetch a single video by ID. Returns None if not found."""
    cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def list_videos(db) -> list[dict]:
    """Return all videos ordered by upload date (newest first)."""
    cursor = await db.execute(
        "SELECT * FROM videos ORDER BY upload_date DESC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_video(db, video_id: int, name: str) -> dict | None:
    """Update a video's name. Returns updated video or None."""
    await db.execute(
        "UPDATE videos SET name = ? WHERE id = ?",
        (name, video_id),
    )
    await db.commit()
    return await get_video(db, video_id)


async def delete_video(db, video_id: int) -> bool:
    """Delete a video record and its files. Returns True if deleted."""
    video = await get_video(db, video_id)
    if video is None:
        return False

    # Remove files
    await file_service.delete_video_file(video["filename"])
    await file_service.delete_thumbnail(video["filename"])

    # Remove database record
    await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    await db.commit()
    return True
