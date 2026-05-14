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

# These are applied incrementally per checkpoint
MIGRATIONS = {
    1: [VIDEOS_SCHEMA],
    # 3: tags + video_tags added here
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
    try:
        for version in range(1, migration_version + 1):
            for stmt in MIGRATIONS.get(version, []):
                await db.execute(stmt)
        await db.commit()
    finally:
        await db.close()
