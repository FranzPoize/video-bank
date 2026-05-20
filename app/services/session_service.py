"""
Session management for opaque authentication tokens.

Only hashed session tokens are stored in the database. Callers receive the raw
token exactly once from ``create_session`` and must use that raw token for later
lookups, revocation, and active-account updates.
"""

from datetime import datetime, timedelta, timezone

import aiosqlite

from app.services import security_service


DEFAULT_SESSION_TTL = timedelta(days=30)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_db_timestamp(value: datetime) -> str:
    """Format datetimes consistently for SQLite string comparison."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_session(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "active_account_id": row["active_account_id"],
        "expires_at": row["expires_at"],
        "revoked_at": row["revoked_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create_session(
    db: aiosqlite.Connection,
    user_id: int,
    active_account_id: int | None = None,
    expires_at: datetime | None = None,
) -> dict:
    """Create a session and return its details including the raw token."""
    token = security_service.create_token()
    token_hash = security_service.hash_token(token)
    expiry = expires_at or (_utc_now() + DEFAULT_SESSION_TTL)

    cursor = await db.execute(
        """
        INSERT INTO sessions (token_hash, user_id, active_account_id, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (token_hash, user_id, active_account_id, _format_db_timestamp(expiry)),
    )
    await db.commit()

    session = await get_session_by_id(db, cursor.lastrowid)
    if session is None:
        raise RuntimeError("Failed to create session")
    session["token"] = token
    return session


async def get_session_by_id(db: aiosqlite.Connection, session_id: int) -> dict | None:
    """Fetch a session by id without exposing its token hash."""
    cursor = await db.execute(
        """
        SELECT id, user_id, active_account_id, expires_at, revoked_at, created_at, updated_at
        FROM sessions
        WHERE id = ?
        """,
        (session_id,),
    )
    row = await cursor.fetchone()
    return _row_to_session(row)


async def load_session(db: aiosqlite.Connection, token: str) -> dict | None:
    """Load a non-revoked, non-expired session by its raw token."""
    token_hash = security_service.hash_token(token)
    cursor = await db.execute(
        """
        SELECT id, user_id, active_account_id, expires_at, revoked_at, created_at, updated_at
        FROM sessions
        WHERE token_hash = ?
          AND revoked_at IS NULL
          AND expires_at > ?
        """,
        (token_hash, _format_db_timestamp(_utc_now())),
    )
    row = await cursor.fetchone()
    return _row_to_session(row)


async def revoke_session(db: aiosqlite.Connection, token: str) -> bool:
    """Revoke a live session by raw token. Returns True when a row changed."""
    token_hash = security_service.hash_token(token)
    cursor = await db.execute(
        """
        UPDATE sessions
        SET revoked_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE token_hash = ?
          AND revoked_at IS NULL
        """,
        (token_hash,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def expire_sessions(db: aiosqlite.Connection) -> int:
    """Mark all expired, non-revoked sessions as revoked."""
    cursor = await db.execute(
        """
        UPDATE sessions
        SET revoked_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE revoked_at IS NULL
          AND expires_at <= ?
        """,
        (_format_db_timestamp(_utc_now()),),
    )
    await db.commit()
    return cursor.rowcount


async def update_active_account(
    db: aiosqlite.Connection,
    token: str,
    active_account_id: int | None,
) -> dict | None:
    """Update a live session's active account and return the updated session."""
    session = await load_session(db, token)
    if session is None:
        return None

    await db.execute(
        """
        UPDATE sessions
        SET active_account_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (active_account_id, session["id"]),
    )
    await db.commit()
    return await load_session(db, token)


async def get_active_account_id(db: aiosqlite.Connection, token: str) -> int | None:
    """Return the active account id for a live session, if any."""
    session = await load_session(db, token)
    if session is None:
        return None
    return session["active_account_id"]
