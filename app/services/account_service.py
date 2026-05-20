"""
Account and membership service helpers.

All functions take an aiosqlite.Connection as the first argument so they remain
simple to test with the in-memory migration v6 schema.
"""

from __future__ import annotations

import aiosqlite


ADMIN_CAPABILITIES = {
    "manage_videos": 1,
    "manage_matches": 1,
    "manage_tags": 1,
    "manage_account_settings": 1,
    "manage_members": 1,
    "admin": 1,
}


async def create_account(db: aiosqlite.Connection, display_name: str) -> dict:
    """Create an account and return it as a dict."""
    clean_display_name = (display_name or "").strip()
    if not clean_display_name:
        raise ValueError("Account name cannot be empty")

    cursor = await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        (clean_display_name,),
    )
    await db.commit()
    account = await get_account(db, cursor.lastrowid)
    if account is None:  # pragma: no cover - defensive database boundary
        raise RuntimeError("Created account could not be loaded")
    return account


async def get_account(db: aiosqlite.Connection, account_id: int) -> dict | None:
    """Return an account by id, or None when it does not exist."""
    cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_first_admin_membership(
    db: aiosqlite.Connection,
    user_id: int,
    account_id: int,
) -> dict:
    """Create the initial all-capabilities admin membership for an account."""
    cursor = await db.execute(
        """
        INSERT INTO account_memberships (
            user_id, account_id, manage_videos, manage_matches, manage_tags,
            manage_account_settings, manage_members, admin, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            user_id,
            account_id,
            ADMIN_CAPABILITIES["manage_videos"],
            ADMIN_CAPABILITIES["manage_matches"],
            ADMIN_CAPABILITIES["manage_tags"],
            ADMIN_CAPABILITIES["manage_account_settings"],
            ADMIN_CAPABILITIES["manage_members"],
            ADMIN_CAPABILITIES["admin"],
        ),
    )
    await db.commit()
    membership = await get_membership_by_id(db, cursor.lastrowid)
    if membership is None:  # pragma: no cover - defensive database boundary
        raise RuntimeError("Created membership could not be loaded")
    return membership


async def create_account_with_admin_membership(
    db: aiosqlite.Connection,
    user_id: int,
    display_name: str,
) -> dict:
    """Create an account and make the user its first administrator."""
    clean_display_name = (display_name or "").strip()
    if not clean_display_name:
        raise ValueError("Account name cannot be empty")

    await db.execute("SAVEPOINT create_account_admin_membership")
    try:
        account_cursor = await db.execute(
            "INSERT INTO accounts (display_name) VALUES (?)",
            (clean_display_name,),
        )
        account_id = account_cursor.lastrowid

        membership_cursor = await db.execute(
            """
            INSERT INTO account_memberships (
                user_id, account_id, manage_videos, manage_matches, manage_tags,
                manage_account_settings, manage_members, admin, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                user_id,
                account_id,
                ADMIN_CAPABILITIES["manage_videos"],
                ADMIN_CAPABILITIES["manage_matches"],
                ADMIN_CAPABILITIES["manage_tags"],
                ADMIN_CAPABILITIES["manage_account_settings"],
                ADMIN_CAPABILITIES["manage_members"],
                ADMIN_CAPABILITIES["admin"],
            ),
        )

        account = await get_account(db, account_id)
        membership = await get_membership_by_id(db, membership_cursor.lastrowid)
        if account is None:  # pragma: no cover - defensive database boundary
            raise RuntimeError("Created account could not be loaded")
        if membership is None:  # pragma: no cover - defensive database boundary
            raise RuntimeError("Created membership could not be loaded")

        await db.execute("RELEASE SAVEPOINT create_account_admin_membership")
        return {"id": account["id"], "account": account, "membership": membership}
    except Exception:
        await db.execute("ROLLBACK TO SAVEPOINT create_account_admin_membership")
        await db.execute("RELEASE SAVEPOINT create_account_admin_membership")
        raise


async def create_account_for_verified_signup(
    db: aiosqlite.Connection,
    user_id: int,
    account_display_name: str | None = None,
) -> dict:
    """Ensure a verified direct-signup user has one account and admin membership.

    Auth verification can call this after marking an email verified. If the user
    already has an active account membership, that account/membership is returned
    instead of creating a duplicate account on repeated verification attempts.
    """
    existing_accounts = await list_active_accounts_for_user(db, user_id)
    if existing_accounts:
        account = existing_accounts[0]
        membership = await get_membership(db, user_id, account["id"])
        if membership is None:  # pragma: no cover - protected by list query
            raise RuntimeError("Active membership could not be loaded")
        return {"id": account["id"], "account": account, "membership": membership}

    display_name = (account_display_name or "My Video Bank").strip()
    return await create_account_with_admin_membership(db, user_id, display_name)


async def list_active_accounts_for_user(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Return accounts where the user currently has an active membership."""
    cursor = await db.execute(
        """
        SELECT a.*
        FROM accounts a
        JOIN account_memberships am ON am.account_id = a.id
        WHERE am.user_id = ?
          AND am.is_active = 1
          AND am.revoked_at IS NULL
        ORDER BY a.display_name COLLATE NOCASE ASC, a.id ASC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def list_accounts_for_user(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Alias for active account listing used by route/auth code."""
    return await list_active_accounts_for_user(db, user_id)


async def get_membership(
    db: aiosqlite.Connection,
    user_id: int,
    account_id: int,
    *,
    active_only: bool = True,
) -> dict | None:
    """Return a user's membership in an account, or None."""
    if active_only:
        cursor = await db.execute(
            """
            SELECT * FROM account_memberships
            WHERE user_id = ?
              AND account_id = ?
              AND is_active = 1
              AND revoked_at IS NULL
            """,
            (user_id, account_id),
        )
    else:
        cursor = await db.execute(
            """
            SELECT * FROM account_memberships
            WHERE user_id = ?
              AND account_id = ?
            """,
            (user_id, account_id),
        )

    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_membership_by_id(
    db: aiosqlite.Connection,
    membership_id: int,
    *,
    active_only: bool = False,
) -> dict | None:
    """Return a membership by id, or None."""
    if active_only:
        cursor = await db.execute(
            """
            SELECT * FROM account_memberships
            WHERE id = ?
              AND is_active = 1
              AND revoked_at IS NULL
            """,
            (membership_id,),
        )
    else:
        cursor = await db.execute(
            """
            SELECT * FROM account_memberships
            WHERE id = ?
            """,
            (membership_id,),
        )

    row = await cursor.fetchone()
    return dict(row) if row else None


async def set_session_active_account(
    db: aiosqlite.Connection,
    session_id: int,
    account_id: int | None,
) -> bool:
    """Set a session's active account id after validating current membership."""
    session = await _get_session(db, session_id)
    if session is None:
        return False

    if account_id is not None:
        membership = await get_membership(db, session["user_id"], account_id)
        if membership is None:
            raise ValueError("User does not have an active membership for this account")

    cursor = await db.execute(
        """
        UPDATE sessions
        SET active_account_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (account_id, session_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_session_active_account_id(
    db: aiosqlite.Connection,
    session_id: int,
) -> int | None:
    """Return the active account id stored on a session, if any."""
    session = await _get_session(db, session_id)
    if session is None:
        return None
    return session["active_account_id"]


async def _get_session(db: aiosqlite.Connection, session_id: int) -> dict | None:
    cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None
