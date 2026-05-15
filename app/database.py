"""
Database connection management and schema initialization.

The database path is configurable via DATABASE_PATH environment variable.
Tests override this to use ":memory:" for isolation.
"""

import os
import aiosqlite

DEFAULT_DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "video_bank.db"),
)

VIDEOS_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

TAGS_TABLE = """
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
"""

VIDEO_TAGS_TABLE = """
CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(video_id, tag_id)
);
"""

IDX_VIDEO_TAGS_VIDEO = """
CREATE INDEX IF NOT EXISTS idx_video_tags_video_id ON video_tags(video_id);
"""

IDX_VIDEO_TAGS_TAG = """
CREATE INDEX IF NOT EXISTS idx_video_tags_tag_id ON video_tags(tag_id);
"""

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

# These are applied incrementally per checkpoint
# Each list element must be a single SQL statement (aiosqlite limitation)
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    2: [],  # Reserved for future structural changes
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


async def get_db(db_path: str | None = None):
    """FastAPI dependency: yield an aiosqlite connection.

    Use `db_path` override for testing; otherwise uses DEFAULT_DB_PATH.
    The caller wraps this in `contextlib.asynccontextmanager` or uses
    FastAPI's Depends with an async generator.
    """
    path = db_path or DEFAULT_DB_PATH
    db_dir = os.path.dirname(path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db(db_path: str | None = None, migration_version: int = 1):
    """Create/upgrade tables to the given migration version."""
    path = db_path or DEFAULT_DB_PATH
    db_dir = os.path.dirname(path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        for version in range(1, migration_version + 1):
            for stmt in MIGRATIONS.get(version, []):
                try:
                    await db.execute(stmt)
                except Exception as e:
                    # Ignore "duplicate column" errors from ALTER TABLE ADD COLUMN
                    err_str = str(e)
                    if "duplicate column name" in err_str:
                        continue
                    raise
        await db.commit()
    finally:
        await db.close()
