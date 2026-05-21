"""
Database connection management and schema initialization.

The database path is configurable via DATABASE_PATH environment variable.
Tests override this to use ":memory:" for isolation.
"""

import os
from collections.abc import Callable

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

IDX_VIDEOS_ACCOUNT = """
CREATE INDEX IF NOT EXISTS idx_videos_account_id ON videos(account_id);
"""

IDX_VIDEOS_ACCOUNT_UPLOAD_DATE = """
CREATE INDEX IF NOT EXISTS idx_videos_account_upload_date
ON videos(account_id, upload_date DESC);
"""

IDX_VIDEOS_ACCOUNT_SOURCE = """
CREATE INDEX IF NOT EXISTS idx_videos_account_source
ON videos(account_id, source_video_id);
"""

IDX_MATCHES_ACCOUNT_DATE = """
CREATE INDEX IF NOT EXISTS idx_matches_account_date ON matches(account_id, match_date DESC);
"""

IDX_TAGS_ACCOUNT = """
CREATE INDEX IF NOT EXISTS idx_tags_account_id ON tags(account_id, name);
"""

IDX_TAGS_ACCOUNT_NAME_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_account_name_unique
ON tags(account_id, name);
"""

IDX_VIDEO_TAGS_VIDEO_TAG = """
CREATE INDEX IF NOT EXISTS idx_video_tags_video_tag
ON video_tags(video_id, tag_id);
"""

IDX_VIDEO_TAGS_TAG_VIDEO = """
CREATE INDEX IF NOT EXISTS idx_video_tags_tag_video
ON video_tags(tag_id, video_id);
"""

IDX_MATCH_VIDEOS_MATCH_VIDEO = """
CREATE INDEX IF NOT EXISTS idx_match_videos_match_video
ON match_videos(match_id, video_id);
"""

IDX_MATCH_VIDEOS_VIDEO_MATCH = """
CREATE INDEX IF NOT EXISTS idx_match_videos_video_match
ON match_videos(video_id, match_id);
"""

USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    normalized_email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_email_verified INTEGER NOT NULL DEFAULT 0 CHECK (is_email_verified IN (0, 1)),
    email_verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

ACCOUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

ACCOUNT_MEMBERSHIPS_TABLE = """
CREATE TABLE IF NOT EXISTS account_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    manage_videos INTEGER NOT NULL DEFAULT 0 CHECK (manage_videos IN (0, 1)),
    manage_matches INTEGER NOT NULL DEFAULT 0 CHECK (manage_matches IN (0, 1)),
    manage_tags INTEGER NOT NULL DEFAULT 0 CHECK (manage_tags IN (0, 1)),
    manage_account_settings INTEGER NOT NULL DEFAULT 0 CHECK (manage_account_settings IN (0, 1)),
    manage_members INTEGER NOT NULL DEFAULT 0 CHECK (manage_members IN (0, 1)),
    admin INTEGER NOT NULL DEFAULT 0 CHECK (admin IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    revoked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, account_id)
);
"""

SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    active_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

EMAIL_VERIFICATION_TOKENS_TABLE = """
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INVITATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    invited_email TEXT NOT NULL,
    invited_normalized_email TEXT NOT NULL,
    inviter_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    manage_videos INTEGER NOT NULL DEFAULT 0 CHECK (manage_videos IN (0, 1)),
    manage_matches INTEGER NOT NULL DEFAULT 0 CHECK (manage_matches IN (0, 1)),
    manage_tags INTEGER NOT NULL DEFAULT 0 CHECK (manage_tags IN (0, 1)),
    manage_account_settings INTEGER NOT NULL DEFAULT 0 CHECK (manage_account_settings IN (0, 1)),
    manage_members INTEGER NOT NULL DEFAULT 0 CHECK (manage_members IN (0, 1)),
    admin INTEGER NOT NULL DEFAULT 0 CHECK (admin IN (0, 1)),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

IDX_USERS_NORMALIZED_EMAIL = """
CREATE INDEX IF NOT EXISTS idx_users_normalized_email ON users(normalized_email);
"""

IDX_ACCOUNT_MEMBERSHIPS_USER_ID = """
CREATE INDEX IF NOT EXISTS idx_account_memberships_user_id ON account_memberships(user_id);
"""

IDX_ACCOUNT_MEMBERSHIPS_ACCOUNT_ID = """
CREATE INDEX IF NOT EXISTS idx_account_memberships_account_id ON account_memberships(account_id);
"""

IDX_ACCOUNT_MEMBERSHIPS_ACTIVE_ACCOUNT = """
CREATE INDEX IF NOT EXISTS idx_account_memberships_active_account
ON account_memberships(account_id, is_active, revoked_at);
"""

IDX_SESSIONS_TOKEN_HASH = """
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
"""

IDX_SESSIONS_USER_ID = """
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
"""

IDX_SESSIONS_ACTIVE_ACCOUNT_ID = """
CREATE INDEX IF NOT EXISTS idx_sessions_active_account_id ON sessions(active_account_id);
"""

IDX_EMAIL_VERIFICATION_TOKENS_TOKEN_HASH = """
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_token_hash
ON email_verification_tokens(token_hash);
"""

IDX_EMAIL_VERIFICATION_TOKENS_USER_ID = """
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user_id
ON email_verification_tokens(user_id);
"""

IDX_INVITATIONS_TOKEN_HASH = """
CREATE INDEX IF NOT EXISTS idx_invitations_token_hash ON invitations(token_hash);
"""

IDX_INVITATIONS_ACCOUNT_STATE = """
CREATE INDEX IF NOT EXISTS idx_invitations_account_state
ON invitations(account_id, accepted_at, revoked_at, expires_at);
"""

IDX_INVITATIONS_INVITED_NORMALIZED_EMAIL = """
CREATE INDEX IF NOT EXISTS idx_invitations_invited_normalized_email
ON invitations(invited_normalized_email);
"""


async def _table_has_column(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Return whether a known application table has a column."""
    allowed_tables = {"videos", "matches", "tags"}
    if table not in allowed_tables:
        raise ValueError(f"Unsupported schema table: {table}")
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in rows)


async def migrate_account_context(db: aiosqlite.Connection):
    """Migration v7: add account context to existing domain rows.

    Existing rows are attached to a deterministic fallback account so tests and
    current single-user installations continue to have account-owned data. The
    exact initial production administrator selection remains a parent/user
    decision outside this schema migration.
    """
    await db.execute(
        """
        INSERT INTO accounts (display_name)
        SELECT ?
        WHERE NOT EXISTS (SELECT 1 FROM accounts)
        """,
        ("Default Account",),
    )
    default_account_rows = await db.execute_fetchall(
        "SELECT MIN(id) AS id FROM accounts"
    )
    default_account_id = default_account_rows[0]["id"]

    if not await _table_has_column(db, "videos", "account_id"):
        await db.execute(
            "ALTER TABLE videos ADD COLUMN account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE"
        )
    if not await _table_has_column(db, "matches", "account_id"):
        await db.execute(
            "ALTER TABLE matches ADD COLUMN account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE"
        )

    if default_account_id is not None:
        await db.execute(
            "UPDATE videos SET account_id = ? WHERE account_id IS NULL",
            (default_account_id,),
        )
        await db.execute(
            "UPDATE matches SET account_id = ? WHERE account_id IS NULL",
            (default_account_id,),
        )

    if not await _table_has_column(db, "tags", "account_id"):
        await db.commit()
        await db.execute("PRAGMA foreign_keys = OFF")
        await db.execute(
            """
            CREATE TABLE tags_v7 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(account_id, name)
            )
            """
        )
        await db.execute(
            """
            INSERT INTO tags_v7 (id, account_id, name)
            SELECT id, ?, name FROM tags
            """,
            (default_account_id,),
        )
        await db.execute("DROP TABLE tags")
        await db.execute("ALTER TABLE tags_v7 RENAME TO tags")
        await db.commit()
        await db.execute("PRAGMA foreign_keys = ON")
    elif default_account_id is not None:
        await db.execute(
            "UPDATE tags SET account_id = ? WHERE account_id IS NULL",
            (default_account_id,),
        )

    account_indexes = [
        IDX_VIDEOS_ACCOUNT,
        IDX_VIDEOS_ACCOUNT_UPLOAD_DATE,
        IDX_VIDEOS_ACCOUNT_SOURCE,
        IDX_MATCHES_ACCOUNT_DATE,
        IDX_TAGS_ACCOUNT,
        IDX_TAGS_ACCOUNT_NAME_UNIQUE,
        IDX_VIDEO_TAGS_VIDEO_TAG,
        IDX_VIDEO_TAGS_TAG_VIDEO,
        IDX_MATCH_VIDEOS_MATCH_VIDEO,
        IDX_MATCH_VIDEOS_VIDEO_MATCH,
    ]
    for stmt in account_indexes:
        await db.execute(stmt)

# These are applied incrementally per checkpoint
# Each list element is either a single SQL statement or a migration helper.
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
    6: [
        USERS_TABLE,
        ACCOUNTS_TABLE,
        ACCOUNT_MEMBERSHIPS_TABLE,
        SESSIONS_TABLE,
        EMAIL_VERIFICATION_TOKENS_TABLE,
        INVITATIONS_TABLE,
        IDX_USERS_NORMALIZED_EMAIL,
        IDX_ACCOUNT_MEMBERSHIPS_USER_ID,
        IDX_ACCOUNT_MEMBERSHIPS_ACCOUNT_ID,
        IDX_ACCOUNT_MEMBERSHIPS_ACTIVE_ACCOUNT,
        IDX_SESSIONS_TOKEN_HASH,
        IDX_SESSIONS_USER_ID,
        IDX_SESSIONS_ACTIVE_ACCOUNT_ID,
        IDX_EMAIL_VERIFICATION_TOKENS_TOKEN_HASH,
        IDX_EMAIL_VERIFICATION_TOKENS_USER_ID,
        IDX_INVITATIONS_TOKEN_HASH,
        IDX_INVITATIONS_ACCOUNT_STATE,
        IDX_INVITATIONS_INVITED_NORMALIZED_EMAIL,
    ],
    7: [migrate_account_context],
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
    db.row_factory = aiosqlite.Row
    try:
        for version in range(1, migration_version + 1):
            for stmt in MIGRATIONS.get(version, []):
                try:
                    if isinstance(stmt, str):
                        await db.execute(stmt)
                    elif isinstance(stmt, Callable):
                        await stmt(db)
                except Exception as e:
                    # Ignore "duplicate column" errors from ALTER TABLE ADD COLUMN
                    err_str = str(e)
                    if "duplicate column name" in err_str:
                        continue
                    raise
        await db.commit()
    finally:
        await db.close()
