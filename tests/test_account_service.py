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


@pytest.mark.asyncio
async def test_list_memberships_for_user_supports_multiple_account_switcher(db):
    user_id = await _create_user(db)
    alpha = await account_service.create_account_with_admin_membership(db, user_id, "Alpha")
    beta = await account_service.create_account_with_admin_membership(db, user_id, "beta")

    memberships = await account_service.list_memberships_for_user(db, user_id)

    assert [membership["account_id"] for membership in memberships] == [alpha["account"]["id"], beta["account"]["id"]]
    assert [membership["account_display_name"] for membership in memberships] == ["Alpha", "beta"]
    assert all(membership["is_active"] == 1 for membership in memberships)


@pytest.mark.asyncio
async def test_switch_session_active_account_rejects_forged_target(db):
    user_id = await _create_user(db)
    other_user_id = await _create_user(db, "switch-forged@example.com")
    owned = await account_service.create_account_with_admin_membership(db, user_id, "Owned")
    forged = await account_service.create_account_with_admin_membership(db, other_user_id, "Forged")
    session_id = await _create_session(db, user_id)

    assert await account_service.switch_session_active_account(db, session_id, owned["account"]["id"]) is True

    with pytest.raises(ValueError, match="active membership"):
        await account_service.switch_session_active_account(db, session_id, forged["account"]["id"])

    assert await account_service.get_session_active_account_id(db, session_id) == owned["account"]["id"]


@pytest.mark.asyncio
async def test_switch_session_active_account_rejects_revoked_membership(db):
    user_id = await _create_user(db)
    revoked = await account_service.create_account_with_admin_membership(db, user_id, "Revoked")
    session_id = await _create_session(db, user_id)
    await db.execute(
        "UPDATE account_memberships SET is_active = 0, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
        (revoked["membership"]["id"],),
    )
    await db.commit()

    with pytest.raises(ValueError, match="active membership"):
        await account_service.switch_session_active_account(db, session_id, revoked["account"]["id"])


@pytest.mark.asyncio
async def test_update_account_display_name_trims_and_returns_account(db):
    user_id = await _create_user(db)
    created = await account_service.create_account_with_admin_membership(db, user_id, "Original")

    account = await account_service.update_account_display_name(db, created["account"]["id"], "  Renamed Team  ")

    assert account is not None
    assert account["display_name"] == "Renamed Team"


@pytest.mark.asyncio
async def test_list_members_for_account_returns_member_summary_and_capabilities(db):
    admin_id = await _create_user(db, "admin-members@example.com")
    member_id = await _create_user(db, "member@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Members")
    await db.execute(
        """
        INSERT INTO account_memberships (
            user_id, account_id, manage_videos, manage_matches, manage_tags,
            manage_account_settings, manage_members, admin, is_active
        ) VALUES (?, ?, 1, 0, 1, 0, 0, 0, 1)
        """,
        (member_id, created["account"]["id"]),
    )
    await db.commit()

    members = await account_service.list_members_for_account(db, created["account"]["id"])

    assert [member["email"] for member in members] == ["admin-members@example.com", "member@example.com"]
    member_summary = members[1]
    assert member_summary["membership_id"] is not None
    assert member_summary["capabilities"] == {
        "manage_videos": True,
        "manage_matches": False,
        "manage_tags": True,
        "manage_account_settings": False,
        "manage_members": False,
        "admin": False,
    }


@pytest.mark.asyncio
async def test_update_member_capabilities_updates_rights_for_planned_rights_route(db):
    """POST /account/members/{membership_id}/rights can save selected capabilities."""
    admin_id = await _create_user(db, "rights-admin@example.com")
    member_id = await _create_user(db, "rights-member@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Rights")
    membership = await account_service.create_or_reactivate_membership(
        db,
        member_id,
        created["account"]["id"],
        {"manage_videos": True},
    )

    updated = await account_service.update_member_capabilities(
        db,
        membership["id"],
        {
            "manage_matches": True,
            "manage_tags": True,
            "manage_members": True,
            "admin": False,
        },
    )

    assert updated is not None
    assert updated["membership_id"] == membership["id"]
    assert updated["capabilities"] == {
        "manage_videos": False,
        "manage_matches": True,
        "manage_tags": True,
        "manage_account_settings": False,
        "manage_members": True,
        "admin": False,
    }


@pytest.mark.asyncio
async def test_update_member_capabilities_rejects_demoting_only_admin(db):
    """Rights updates preserve last-admin protection."""
    admin_id = await _create_user(db, "only-admin-rights@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Only Admin")

    with pytest.raises(ValueError, match="Cannot demote the only administrator"):
        await account_service.update_member_capabilities(
            db,
            created["membership"]["id"],
            {"admin": False, "manage_members": True},
        )

    still_admin = await account_service.get_membership_by_id(db, created["membership"]["id"])
    assert still_admin["admin"] == 1


@pytest.mark.asyncio
async def test_remove_member_revokes_membership_for_planned_remove_route(db):
    """POST /account/members/{membership_id}/remove revokes non-last-admin members."""
    admin_id = await _create_user(db, "remove-admin@example.com")
    member_id = await _create_user(db, "remove-member@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Remove")
    membership = await account_service.create_or_reactivate_membership(
        db,
        member_id,
        created["account"]["id"],
        {"manage_videos": True},
    )

    removed = await account_service.remove_member(db, membership["id"])

    assert removed is True
    assert await account_service.get_membership(db, member_id, created["account"]["id"]) is None
    revoked = await account_service.get_membership(db, member_id, created["account"]["id"], active_only=False)
    assert revoked["is_active"] == 0
    assert revoked["revoked_at"] is not None


@pytest.mark.asyncio
async def test_remove_member_rejects_removing_only_admin(db):
    """Member removal preserves last-admin protection."""
    admin_id = await _create_user(db, "only-admin-remove@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Only Remove")

    with pytest.raises(ValueError, match="Cannot remove the only administrator"):
        await account_service.remove_member(db, created["membership"]["id"])

    assert await account_service.get_membership_by_id(db, created["membership"]["id"], active_only=True) is not None


@pytest.mark.asyncio
async def test_activate_membership_from_invitation_reactivates_revoked_membership(db):
    """Invitation acceptance restores a removed member with invitation capabilities."""
    admin_id = await _create_user(db, "invite-admin@example.com")
    member_id = await _create_user(db, "invited-member@example.com")
    created = await account_service.create_account_with_admin_membership(db, admin_id, "Invite")
    membership = await account_service.create_or_reactivate_membership(
        db,
        member_id,
        created["account"]["id"],
        {"manage_videos": True},
    )
    await account_service.remove_member(db, membership["id"])
    cursor = await db.execute(
        """
        INSERT INTO invitations (
            account_id, invited_email, invited_normalized_email, inviter_user_id,
            manage_videos, manage_matches, manage_tags, manage_account_settings,
            manage_members, admin, token_hash, expires_at
        ) VALUES (?, ?, ?, ?, 0, 1, 1, 0, 0, 0, ?, datetime('now', '+1 day'))
        """,
        (
            created["account"]["id"],
            "invited-member@example.com",
            "invited-member@example.com",
            admin_id,
            "token-hash-reactivate",
        ),
    )
    await db.commit()
    invitation_row = await (await db.execute("SELECT * FROM invitations WHERE id = ?", (cursor.lastrowid,))).fetchone()

    reactivated = await account_service.activate_membership_from_invitation(db, member_id, invitation_row)

    assert reactivated["id"] == membership["id"]
    assert reactivated["is_active"] == 1
    assert reactivated["revoked_at"] is None
    assert reactivated["manage_videos"] == 0
    assert reactivated["manage_matches"] == 1
    assert reactivated["manage_tags"] == 1
