"""Route tests for invitation acceptance and signup integration."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.services import account_service, auth_service, invitation_service, permission_service, security_service, session_service
from tests.conftest import create_test_user_with_account, login_test_user


@pytest.mark.asyncio
async def test_admin_can_create_invitation(client, db, auth_context, monkeypatch):
    """Admins can create invitations and send invitation email."""
    sent = {}

    def fake_send_invitation_email(recipient, *, inviter_email, account_name, invitation_url, delivery_mode=None):
        sent.update(
            recipient=recipient,
            inviter_email=inviter_email,
            account_name=account_name,
            invitation_url=invitation_url,
        )
        return {"accepted": True, "kind": "invitation"}

    monkeypatch.setattr("app.routes.invitations.email_service.send_invitation_email", fake_send_invitation_email)

    response = await client.post(
        "/account/invitations",
        data={"email": "invitee@example.com", "capabilities": ["manage_videos"]},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/account/invitations/new?sent=1"
    assert sent["recipient"] == "invitee@example.com"
    assert "/invitations/accept?token=" in sent["invitation_url"]

    followup = await client.get(response.headers["location"])
    assert followup.status_code == 200
    assert "The invitation email includes a secure acceptance link" in followup.text
    assert "invitee@example.com" in followup.text


@pytest.mark.asyncio
async def test_new_user_accepts_after_signup_and_email_verification(client, db, monkeypatch):
    """A new invitee can signup with token context and gets membership after verification."""
    owner = await create_test_user_with_account(db, email="owner@example.com", account_name="Team Videos")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="new-user@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={"manage_matches": True},
    )
    sent = {}

    def fake_send_verification_email(recipient, verification_url, *, invitation_url=None, delivery_mode=None):
        sent["recipient"] = recipient
        sent["verification_url"] = verification_url
        sent["invitation_url"] = invitation_url
        return {"accepted": True, "kind": "verification"}

    monkeypatch.setattr("app.routes.auth.email_service.send_verification_email", fake_send_verification_email)

    accept_page = await client.get(f"/invitations/accept?token={invitation['token']}")
    assert accept_page.status_code == 200
    assert "Team Videos" in accept_page.text
    assert "Use the invited email address when you continue" in accept_page.text

    signup_page = await client.get(f"/signup?invitation_token={invitation['token']}")
    assert signup_page.status_code == 200
    assert 'name="invitation_token"' in signup_page.text
    assert "After verification, your membership will be activated automatically" in signup_page.text

    signup = await client.post(
        "/signup",
        data={
            "email": "new-user@example.com",
            "password": "correct-password",
            "invitation_token": invitation["token"],
        },
    )
    assert signup.status_code == 200
    assert sent["recipient"] == "new-user@example.com"
    assert f"invitation_token={invitation['token']}" in sent["verification_url"]
    verification_token = parse_qs(urlparse(sent["verification_url"]).query)["token"][0]

    verified = await client.get(f"/verify-email?token={verification_token}&invitation_token={invitation['token']}")

    assert verified.status_code == 200
    assert "Your pending invitation has been activated" in verified.text
    user = await auth_service.get_user_by_email(db, "new-user@example.com")
    membership = await (
        await db.execute(
            "SELECT * FROM account_memberships WHERE user_id = ? AND account_id = ?",
            (user["id"], owner["account"]["id"]),
        )
    ).fetchone()
    assert membership is not None
    assert membership["manage_matches"] == 1
    accepted = await invitation_service.get_invitation_by_id(db, invitation["id"])
    assert accepted["accepted_at"] is not None


@pytest.mark.asyncio
async def test_invitation_create_persists_selected_capabilities(client, db, auth_context, monkeypatch):
    """Admin-selected capability checkboxes are stored on the invitation."""
    monkeypatch.setattr(
        "app.routes.invitations.email_service.send_invitation_email",
        lambda *args, **kwargs: {"accepted": True, "kind": "invitation"},
    )

    response = await client.post(
        "/account/invitations",
        data={
            "email": "capability-invitee@example.com",
            "capabilities": [permission_service.MANAGE_VIDEOS, permission_service.MANAGE_TAGS],
        },
    )

    assert response.status_code == 303
    invitation = await (await db.execute(
        "SELECT * FROM invitations WHERE invited_normalized_email = ?",
        ("capability-invitee@example.com",),
    )).fetchone()
    assert invitation["manage_videos"] == 1
    assert invitation["manage_tags"] == 1
    assert invitation["manage_matches"] == 0


@pytest.mark.asyncio
async def test_member_without_manage_members_cannot_invite(client, db):
    """A non-admin account member without manage_members cannot create invitations."""
    await login_test_user(
        client,
        db,
        email="limited@example.com",
        capabilities={"manage_members": False, "admin": False},
    )

    response = await client.post(
        "/account/invitations",
        data={"email": "denied@example.com", "capabilities": [permission_service.MANAGE_VIDEOS]},
    )

    assert response.status_code == 403
    count = await (await db.execute("SELECT COUNT(*) AS count FROM invitations")).fetchone()
    assert count["count"] == 0


@pytest.mark.asyncio
async def test_email_send_failure_leaves_pending_invitation_and_safe_error(client, db, auth_context, monkeypatch, caplog):
    """If email delivery fails, the pending invitation remains and the response is safe."""
    def fail_send(*args, **kwargs):
        raise RuntimeError("smtp password leaked detail")

    monkeypatch.setattr("app.routes.invitations.email_service.send_invitation_email", fail_send)

    response = await client.post(
        "/account/invitations",
        data={"email": "mail-failure@example.com", "capabilities": [permission_service.MANAGE_MEMBERS]},
    )

    assert response.status_code == 500
    assert "We created the invitation, but could not send the email" in response.text
    assert "smtp password leaked detail" not in response.text
    invitation = await (await db.execute(
        "SELECT * FROM invitations WHERE invited_normalized_email = ?",
        ("mail-failure@example.com",),
    )).fetchone()
    assert invitation is not None
    assert invitation["accepted_at"] is None
    assert invitation["revoked_at"] is None
    assert any("Failed to send invitation email" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_expired_revoked_and_used_invitations_show_safe_errors(client, db):
    """Expired, revoked, used, and unknown invitation tokens render safe errors."""
    owner = await create_test_user_with_account(db, email="states-owner@example.com", account_name="State Team")
    expired = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="expired@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={},
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    revoked = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="revoked@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={},
    )
    await invitation_service.revoke_invitation(db, revoked["id"], owner["account"]["id"], owner["user_id"])

    used_user = await auth_service.create_unverified_user(db, "used@example.com", "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (used_user["id"],))
    await db.commit()
    used = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="used@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={},
    )
    await invitation_service.accept_invitation(db, used["token"], used_user["id"])

    for token in (expired["token"], revoked["token"], used["token"], "missing-token"):
        response = await client.get(f"/invitations/accept?token={token}")
        assert response.status_code == 200
        assert "This invitation link is invalid or no longer available" in response.text
        assert "Ask the account admin to send a new invitation" in response.text


@pytest.mark.asyncio
async def test_existing_verified_user_accepts_invitation(client, db):
    """A logged-in verified invitee can accept and receive selected capabilities."""
    owner = await create_test_user_with_account(db, email="existing-owner@example.com", account_name="Existing Team")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="existing-invitee@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={permission_service.MANAGE_MATCHES: True, permission_service.MANAGE_TAGS: True},
    )
    user = await auth_service.create_unverified_user(db, "existing-invitee@example.com", "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (user["id"],))
    await db.commit()
    personal = await account_service.create_account_with_admin_membership(db, user["id"], "Personal Team")
    session = await session_service.create_session(db, user["id"], active_account_id=personal["account"]["id"])
    client.cookies.set("video_bank_session", session["token"])

    response = await client.post("/invitations/accept", data={"token": invitation["token"]})

    assert response.status_code == 303
    assert response.headers["location"] == "/account/settings?invitation_accepted=1"
    membership = await account_service.get_membership(db, user["id"], owner["account"]["id"])
    assert membership is not None
    assert membership["manage_matches"] == 1
    assert membership["manage_tags"] == 1
    assert membership["manage_videos"] == 0


@pytest.mark.asyncio
async def test_unauthenticated_post_accept_redirects_to_signup_with_invitation_token(client, db):
    """Anonymous invitees are redirected after POST with invitation token context preserved."""
    owner = await create_test_user_with_account(db, email="signup-owner@example.com", account_name="Signup Team")
    invitation = await invitation_service.create_invitation(
        db,
        account_id=owner["account"]["id"],
        invited_email="signup-invitee@example.com",
        inviter_user_id=owner["user_id"],
        capabilities={},
    )

    response = await client.post("/invitations/accept", data={"token": invitation["token"]})

    assert response.status_code == 303
    assert response.headers["location"] == f"/signup?invitation_token={invitation['token']}"

    signup_page = await client.get(response.headers["location"])
    assert signup_page.status_code == 200
    assert f'name="invitation_token" value="{invitation["token"]}"' in signup_page.text


@pytest.mark.asyncio
async def test_invalid_post_accept_redirects_to_safe_get(client):
    """Invalid POST accept attempts redirect to the GET invitation page for safe rendering."""
    response = await client.post("/invitations/accept", data={"token": "missing-token"})

    assert response.status_code == 303
    assert response.headers["location"] == "/invitations/accept?token=missing-token"

    result = await client.get(response.headers["location"])
    assert result.status_code == 200
    assert "This invitation link is invalid or no longer available" in result.text
