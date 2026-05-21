"""Tests for database schema migrations."""

import sqlite3

import aiosqlite
import pytest

from app.database import init_db


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


@pytest.mark.asyncio
async def test_account_context_schema_columns_and_indexes_available(db):
    """Migration v7 adds account ownership columns and account lookup indexes."""
    for table in ("videos", "matches", "tags"):
        columns = await db.execute_fetchall(f"PRAGMA table_info({table})")
        assert "account_id" in {row["name"] for row in columns}

    expected_indexes = {
        "idx_videos_account_id",
        "idx_videos_account_upload_date",
        "idx_videos_account_source",
        "idx_matches_account_date",
        "idx_tags_account_id",
        "idx_tags_account_name_unique",
        "idx_video_tags_video_tag",
        "idx_video_tags_tag_video",
        "idx_match_videos_match_video",
        "idx_match_videos_video_match",
    }
    placeholders = ", ".join("?" for _ in expected_indexes)
    index_rows = await db.execute_fetchall(
        f"SELECT name FROM sqlite_master WHERE type = 'index' AND name IN ({placeholders})",
        tuple(sorted(expected_indexes)),
    )
    assert {row["name"] for row in index_rows} == expected_indexes


@pytest.mark.asyncio
async def test_tags_are_unique_per_account_not_globally(db):
    """Migration v7 allows the same tag name in different accounts only."""
    account_a = (await db.execute_fetchall("SELECT MIN(id) AS id FROM accounts"))[0]["id"]
    account_b_cursor = await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        ("Second Account",),
    )
    account_b = account_b_cursor.lastrowid

    await db.execute(
        "INSERT INTO tags (account_id, name) VALUES (?, ?)",
        (account_a, "Scout"),
    )
    await db.execute(
        "INSERT INTO tags (account_id, name) VALUES (?, ?)",
        (account_b, "Scout"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO tags (account_id, name) VALUES (?, ?)",
            (account_a, "Scout"),
        )


@pytest.mark.asyncio
async def test_migration_v7_assigns_existing_rows_to_default_account(tmp_path):
    """Existing videos, matches, and tags receive a deterministic account id."""
    db_path = tmp_path / "schema-v7-existing.db"
    await init_db(str(db_path), migration_version=6)

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute(
        """
        INSERT INTO videos (name, filename, original_name, mime_type, file_size)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Video", "video.mp4", "video.mp4", "video/mp4", 10),
    )
    await db.execute(
        "INSERT INTO matches (name, match_date) VALUES (?, ?)",
        ("Match", "2026-05-20"),
    )
    await db.execute("INSERT INTO tags (name) VALUES (?)", ("Important",))
    await db.commit()
    await db.close()

    await init_db(str(db_path), migration_version=7)

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        account = (await db.execute_fetchall("SELECT id, display_name FROM accounts"))[0]
        assert account["display_name"] == "Default Account"

        video = (await db.execute_fetchall("SELECT account_id FROM videos"))[0]
        match = (await db.execute_fetchall("SELECT account_id FROM matches"))[0]
        tag = (await db.execute_fetchall("SELECT account_id FROM tags"))[0]
        assert video["account_id"] == account["id"]
        assert match["account_id"] == account["id"]
        assert tag["account_id"] == account["id"]

        await init_db(str(db_path), migration_version=7)
        accounts = await db.execute_fetchall("SELECT COUNT(*) AS count FROM accounts")
        assert accounts[0]["count"] == 1
    finally:
        await db.close()
