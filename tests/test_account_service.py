"""Tests for account and membership service helpers."""

import sqlite3

import pytest

from app.services import account_service


async def _create_user(db, email: str = "user@example.com") -> int:
    cursor = await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, ?)
        """,
        (email, email.strip().lower(), "hash", 1),
    )
    await db.commit()
    return cursor.lastrowid


async def _create_session(db, user_id: int) -> int:
    cursor = await db.execute(
        """
        INSERT INTO sessions (token_hash, user_id, expires_at)
        VALUES (?, ?, datetime('now', '+1 day'))
        """,
        (f"session-{user_id}", user_id),
    )
    await db.commit()
    return cursor.lastrowid


@pytest.mark.asyncio
async def test_create_account_and_first_admin_membership(db):
    user_id = await _create_user(db)

    account = await account_service.create_account(db, "Team Account")
    membership = await account_service.create_first_admin_membership(db, user_id, account["id"])

    assert account["display_name"] == "Team Account"
    assert membership["user_id"] == user_id
    assert membership["account_id"] == account["id"]
    assert membership["admin"] == 1
    assert membership["manage_videos"] == 1
    assert membership["manage_matches"] == 1
    assert membership["manage_tags"] == 1
    assert membership["manage_account_settings"] == 1
    assert membership["manage_members"] == 1
    assert membership["is_active"] == 1


@pytest.mark.asyncio
async def test_create_account_for_verified_signup_creates_admin_membership(db):
    user_id = await _create_user(db, "Coach@Example.com")

    result = await account_service.create_account_for_verified_signup(
        db,
        user_id,
        account_display_name="Coach's Video Bank",
    )

    account = result["account"]
    membership = result["membership"]

    assert account["display_name"] == "Coach's Video Bank"
    assert membership["user_id"] == user_id
    assert membership["account_id"] == account["id"]
    assert membership["admin"] == 1


@pytest.mark.asyncio
async def test_create_account_with_admin_membership_rolls_back_account_on_membership_failure(db):
    with pytest.raises(sqlite3.IntegrityError):
        await account_service.create_account_with_admin_membership(db, 999, "Orphaned Account")

    cursor = await db.execute(
        "SELECT * FROM accounts WHERE display_name = ?",
        ("Orphaned Account",),
    )
    assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_create_account_for_verified_signup_is_idempotent_for_existing_membership(db):
    user_id = await _create_user(db)
    first = await account_service.create_account_for_verified_signup(db, user_id, "Existing Account")

    second = await account_service.create_account_for_verified_signup(db, user_id, "Ignored Account")

    accounts = await account_service.list_active_accounts_for_user(db, user_id)
    assert len(accounts) == 1
    assert second["account"]["id"] == first["account"]["id"]
    assert second["membership"]["id"] == first["membership"]["id"]


@pytest.mark.asyncio
async def test_list_active_accounts_for_user_excludes_revoked_memberships(db):
    user_id = await _create_user(db)
    active = await account_service.create_account_with_admin_membership(db, user_id, "Active")
    revoked = await account_service.create_account_with_admin_membership(db, user_id, "Revoked")
    await db.execute(
        "UPDATE account_memberships SET is_active = 0, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
        (revoked["membership"]["id"],),
    )
    await db.commit()

    accounts = await account_service.list_active_accounts_for_user(db, user_id)

    assert [account["id"] for account in accounts] == [active["account"]["id"]]


@pytest.mark.asyncio
async def test_membership_lookup_respects_active_only(db):
    user_id = await _create_user(db)
    created = await account_service.create_account_with_admin_membership(db, user_id, "Team")

    membership = await account_service.get_membership(db, user_id, created["account"]["id"])
    assert membership["id"] == created["membership"]["id"]

    await db.execute(
        "UPDATE account_memberships SET is_active = 0, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
        (membership["id"],),
    )
    await db.commit()

    assert await account_service.get_membership(db, user_id, created["account"]["id"]) is None
    inactive = await account_service.get_membership(
        db,
        user_id,
        created["account"]["id"],
        active_only=False,
    )
    assert inactive["id"] == membership["id"]


@pytest.mark.asyncio
async def test_set_and_get_active_account_for_session_requires_membership(db):
    user_id = await _create_user(db)
    other_user_id = await _create_user(db, "other@example.com")
    created = await account_service.create_account_with_admin_membership(db, user_id, "Team")
    other = await account_service.create_account_with_admin_membership(db, other_user_id, "Other")
    session_id = await _create_session(db, user_id)

    updated = await account_service.set_session_active_account(db, session_id, created["account"]["id"])

    assert updated is True
    assert await account_service.get_session_active_account_id(db, session_id) == created["account"]["id"]

    with pytest.raises(ValueError, match="active membership"):
        await account_service.set_session_active_account(db, session_id, other["account"]["id"])


@pytest.mark.asyncio
async def test_create_account_rejects_empty_display_name(db):
    with pytest.raises(ValueError, match="Account name cannot be empty"):
        await account_service.create_account(db, "   ")
