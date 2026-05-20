"""
Tests for persistent opaque session management.

Run with: pytest tests/test_session_service.py -v
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import security_service, session_service


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_user_and_account(db) -> tuple[int, int]:
    cursor = await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, 1)
        """,
        (
            "user@example.com",
            "user@example.com",
            security_service.hash_password("password"),
        ),
    )
    user_id = cursor.lastrowid
    cursor = await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        ("Test Account",),
    )
    account_id = cursor.lastrowid
    await db.execute(
        """
        INSERT INTO account_memberships (user_id, account_id, admin)
        VALUES (?, ?, 1)
        """,
        (user_id, account_id),
    )
    await db.commit()
    return user_id, account_id


@pytest.mark.asyncio
async def test_create_session_stores_only_hashed_token(db):
    """Session creation returns the raw token but persists only its hash."""
    user_id, account_id = await _create_user_and_account(db)
    expires_at = _utc_now() + timedelta(days=1)

    session = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=expires_at,
    )

    assert session["token"]
    assert session["user_id"] == user_id
    assert session["active_account_id"] == account_id

    cursor = await db.execute("SELECT token_hash FROM sessions WHERE id = ?", (session["id"],))
    row = await cursor.fetchone()

    assert row["token_hash"] == security_service.hash_token(session["token"])
    assert row["token_hash"] != session["token"]


@pytest.mark.asyncio
async def test_load_session_by_raw_token_includes_user_and_active_account(db):
    """A valid raw token resolves to its live session details."""
    user_id, account_id = await _create_user_and_account(db)
    created = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() + timedelta(days=1),
    )

    loaded = await session_service.load_session(db, created["token"])

    assert loaded is not None
    assert loaded["id"] == created["id"]
    assert loaded["user_id"] == user_id
    assert loaded["active_account_id"] == account_id
    assert "token_hash" not in loaded


@pytest.mark.asyncio
async def test_load_session_rejects_expired_session(db):
    """Expired sessions cannot be loaded even with the correct token."""
    user_id, account_id = await _create_user_and_account(db)
    created = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() - timedelta(seconds=1),
    )

    assert await session_service.load_session(db, created["token"]) is None


@pytest.mark.asyncio
async def test_revoke_session_prevents_reuse(db):
    """Revoked sessions cannot be loaded again."""
    user_id, account_id = await _create_user_and_account(db)
    created = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() + timedelta(days=1),
    )

    assert await session_service.revoke_session(db, created["token"]) is True
    assert await session_service.load_session(db, created["token"]) is None


@pytest.mark.asyncio
async def test_expire_sessions_revokes_only_expired_live_sessions(db):
    """Bulk expiry marks expired sessions revoked and leaves live sessions usable."""
    user_id, account_id = await _create_user_and_account(db)
    expired = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() - timedelta(minutes=5),
    )
    live = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() + timedelta(minutes=5),
    )

    expired_count = await session_service.expire_sessions(db)

    assert expired_count == 1
    assert await session_service.load_session(db, expired["token"]) is None
    assert await session_service.load_session(db, live["token"]) is not None

    cursor = await db.execute("SELECT revoked_at FROM sessions WHERE id = ?", (expired["id"],))
    row = await cursor.fetchone()
    assert row["revoked_at"] is not None


@pytest.mark.asyncio
async def test_update_and_get_active_account(db):
    """The active account can be changed and read through the raw session token."""
    user_id, first_account_id = await _create_user_and_account(db)
    cursor = await db.execute("INSERT INTO accounts (display_name) VALUES (?)", ("Second Account",))
    second_account_id = cursor.lastrowid
    await db.execute(
        "INSERT INTO account_memberships (user_id, account_id, admin) VALUES (?, ?, 1)",
        (user_id, second_account_id),
    )
    await db.commit()
    created = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=first_account_id,
        expires_at=_utc_now() + timedelta(days=1),
    )

    updated = await session_service.update_active_account(db, created["token"], second_account_id)

    assert updated is not None
    assert updated["active_account_id"] == second_account_id
    assert await session_service.get_active_account_id(db, created["token"]) == second_account_id


@pytest.mark.asyncio
async def test_update_active_account_rejects_invalid_or_inactive_session(db):
    """Active account updates fail closed for invalid tokens and expired sessions."""
    user_id, account_id = await _create_user_and_account(db)
    expired = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=account_id,
        expires_at=_utc_now() - timedelta(days=1),
    )

    assert await session_service.update_active_account(db, "not-a-token", account_id) is None
    assert await session_service.update_active_account(db, expired["token"], account_id) is None
