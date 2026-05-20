"""Tests for database schema migrations."""

import pytest


@pytest.mark.asyncio
async def test_user_account_schema_tables_and_indexes_available(db):
    """Migration v6 creates the user/account foundation schema."""
    expected_tables = {
        "users",
        "accounts",
        "account_memberships",
        "sessions",
        "email_verification_tokens",
        "invitations",
    }
    rows = await db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?, ?, ?, ?)",
        tuple(sorted(expected_tables)),
    )
    assert {row["name"] for row in rows} == expected_tables

    expected_indexes = {
        "idx_users_normalized_email",
        "idx_account_memberships_user_id",
        "idx_account_memberships_account_id",
        "idx_account_memberships_active_account",
        "idx_sessions_token_hash",
        "idx_sessions_user_id",
        "idx_sessions_active_account_id",
        "idx_email_verification_tokens_token_hash",
        "idx_email_verification_tokens_user_id",
        "idx_invitations_token_hash",
        "idx_invitations_account_state",
        "idx_invitations_invited_normalized_email",
    }
    index_rows = await db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(sorted(expected_indexes)),
    )
    assert {row["name"] for row in index_rows} == expected_indexes


@pytest.mark.asyncio
async def test_user_account_schema_accepts_core_relationships(db):
    """Core auth/account tables can store related foundation records."""
    user_cursor = await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, ?)
        """,
        ("Person@Example.com", "person@example.com", "hash", 1),
    )
    user_id = user_cursor.lastrowid

    account_cursor = await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        ("Demo Account",),
    )
    account_id = account_cursor.lastrowid

    await db.execute(
        """
        INSERT INTO account_memberships (
            user_id, account_id, manage_videos, manage_matches, manage_tags,
            manage_account_settings, manage_members, admin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, account_id, 1, 1, 1, 1, 1, 1),
    )
    await db.execute(
        """
        INSERT INTO sessions (token_hash, user_id, active_account_id, expires_at)
        VALUES (?, ?, ?, datetime('now', '+1 day'))
        """,
        ("session-hash", user_id, account_id),
    )
    await db.execute(
        """
        INSERT INTO email_verification_tokens (token_hash, user_id, expires_at)
        VALUES (?, ?, datetime('now', '+1 day'))
        """,
        ("verify-hash", user_id),
    )
    await db.execute(
        """
        INSERT INTO invitations (
            account_id, invited_email, invited_normalized_email, inviter_user_id,
            manage_videos, token_hash, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+1 day'))
        """,
        (account_id, "Invitee@Example.com", "invitee@example.com", user_id, 1, "invite-hash"),
    )
    await db.commit()

    rows = await db.execute_fetchall("SELECT COUNT(*) AS count FROM account_memberships")
    assert rows[0]["count"] == 1
