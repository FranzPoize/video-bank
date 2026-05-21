"""Service tests for account invitations."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import account_service, auth_service, invitation_service, permission_service, security_service
from tests.conftest import create_test_user_with_account


@pytest.mark.asyncio
async def test_existing_verified_user_accepts_invitation(db):
    """A verified invited user can accept and receive the selected capabilities."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    invited = await auth_service.create_unverified_user(db, "invitee@example.com", "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (invited["id"],))
    await db.commit()

    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="Invitee@Example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"manage_videos": True, "manage_tags": True},
    )

    result = await invitation_service.accept_invitation(db, invitation["token"], invited["id"])
    membership = result["membership"]

    assert membership["account_id"] == owner["account"]["id"]
    assert membership["manage_videos"] == 1
    assert membership["manage_tags"] == 1
    accepted = await invitation_service.get_invitation_by_id(db, invitation["id"])
    assert accepted["accepted_at"] is not None


@pytest.mark.asyncio
async def test_create_invitation_hashes_token_and_normalizes_email(db):
    """Invitation tokens are stored hashed and emails are stored normalized."""
    owner = await create_test_user_with_account(db, email="owner@example.com")

    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="  Invitee@Example.COM  ",
        inviter_user_id=owner["user_id"],
    )

    row = await (await db.execute("SELECT * FROM invitations WHERE id = ?", (invitation["id"],))).fetchone()
    assert row["invited_email"] == "Invitee@Example.COM"
    assert row["invited_normalized_email"] == "invitee@example.com"
    assert row["token_hash"] == security_service.hash_token(invitation["token"])
    assert row["token_hash"] != invitation["token"]
    assert await invitation_service.get_invitation_by_token(db, invitation["token"]) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "message"),
    [
        ("revoked", "revoked"),
        ("expired", "expired"),
        ("accepted", "already accepted"),
    ],
)
async def test_pending_invitation_rejects_revoked_expired_and_accepted(db, state, message):
    """Non-pending invitation states cannot be accepted or loaded as pending."""
    owner = await create_test_user_with_account(db, email=f"owner-{state}@example.com")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email=f"invitee-{state}@example.com",
        inviter_user_id=owner["user_id"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    if state == "revoked":
        await invitation_service.revoke_invitation(db, invitation["id"])
    elif state == "expired":
        await db.execute(
            "UPDATE invitations SET expires_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), invitation["id"]),
        )
        await db.commit()
    else:
        await db.execute("UPDATE invitations SET accepted_at = CURRENT_TIMESTAMP WHERE id = ?", (invitation["id"],))
        await db.commit()

    with pytest.raises(ValueError, match=message):
        await invitation_service.accept_invitation(db, invitation["token"], owner["user_id"])


@pytest.mark.asyncio
async def test_accept_invitation_rejects_email_mismatch(db):
    """A signed-in user cannot accept another email address's invitation."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    other = await create_test_user_with_account(db, email="other@example.com", account_name="Other")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="invitee@example.com",
        inviter_user_id=owner["user_id"],
    )

    with pytest.raises(ValueError, match="Invitation email does not match"):
        await invitation_service.accept_invitation(db, invitation["token"], other["user_id"])


@pytest.mark.asyncio
async def test_anonymous_accept_reports_signup_or_verification_required(db):
    """Anonymous invitation checks return safe next-step statuses."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    new_user_invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="new-user@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"manage_videos": True},
    )
    unverified = await auth_service.create_unverified_user(db, "unverified@example.com", "password")
    unverified_invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="unverified@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"manage_members": True},
    )

    signup = await invitation_service.accept_invitation(db, new_user_invitation["token"])
    verification = await invitation_service.accept_invitation(db, unverified_invitation["token"])

    assert signup["status"] == "signup_required"
    assert signup["invited_email"] == "new-user@example.com"
    assert signup["capabilities"]["manage_videos"] is True
    assert verification["status"] == "verification_required"
    assert verification["user_id"] == unverified["id"]
    assert verification["capabilities"]["manage_members"] is True


@pytest.mark.asyncio
async def test_admin_invitation_persists_all_capabilities_for_new_membership(db):
    """Accepting an admin invite persists every capability flag enabled."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    invited = await auth_service.create_unverified_user(db, "admin-invitee@example.com", "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (invited["id"],))
    await db.commit()
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="admin-invitee@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"admin": True, "manage_videos": False},
    )

    result = await invitation_service.accept_invitation(db, invitation["token"], invited["id"])

    assert {capability: result["membership"][capability] for capability in permission_service.ALL_CAPABILITIES} == {
        capability: 1 for capability in permission_service.ALL_CAPABILITIES
    }


@pytest.mark.asyncio
async def test_accept_invitation_reactivates_inactive_membership_and_updates_capabilities(db):
    """A removed member is reactivated with invitation capabilities."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    invited = await auth_service.create_unverified_user(db, "removed@example.com", "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (invited["id"],))
    await db.commit()
    membership = await account_service.create_or_reactivate_membership(
        db,
        invited["id"],
        owner["account"]["id"],
        {"manage_videos": True},
    )
    await account_service.remove_member(db, membership["id"])
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="removed@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"admin": True, "manage_videos": False},
    )

    result = await invitation_service.accept_invitation(db, invitation["token"], invited["id"])
    reactivated = result["membership"]

    assert reactivated["id"] == membership["id"]
    assert reactivated["is_active"] == 1
    assert reactivated["revoked_at"] is None
    assert {capability: reactivated[capability] for capability in permission_service.ALL_CAPABILITIES} == {
        capability: 1 for capability in permission_service.ALL_CAPABILITIES
    }


@pytest.mark.asyncio
async def test_accept_invitation_preserves_last_admin_when_updating_existing_membership(db):
    """An invite cannot demote/update the account's existing only admin."""
    owner = await create_test_user_with_account(db, email="only-admin@example.com")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="only-admin@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"admin": False, "manage_members": True},
    )

    with pytest.raises(ValueError, match="Cannot demote the only administrator"):
        await invitation_service.accept_invitation(db, invitation["token"], owner["user_id"])

    membership = await account_service.get_membership(db, owner["user_id"], owner["account"]["id"])
    not_accepted = await invitation_service.get_invitation_by_id(db, invitation["id"])
    assert membership["admin"] == 1
    assert not_accepted["accepted_at"] is None


@pytest.mark.asyncio
async def test_unverified_user_cannot_accept_until_verification(db):
    """Unverified users are blocked from activating invitation membership."""
    owner = await create_test_user_with_account(db, email="owner@example.com")
    invited = await auth_service.create_unverified_user(db, "invitee@example.com", "password")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="invitee@example.com",
        inviter_user_id=owner["user_id"],
    )

    with pytest.raises(ValueError, match="Email verification is required"):
        await invitation_service.accept_invitation(db, invitation["token"], invited["id"])
