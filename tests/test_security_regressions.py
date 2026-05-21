"""Security regression coverage for permission-gated UI and mutations."""

from datetime import datetime, timedelta, timezone

import pytest

from app.dependencies import SESSION_COOKIE_NAME
from app.services import account_service, auth_service, invitation_service, permission_service, security_service, session_service
from tests.conftest import create_test_user_with_account, create_test_video, login_test_user


async def _add_limited_member(db, account_id: int, email: str, **capabilities) -> dict:
    """Create a verified user with a membership in an existing account."""
    user = await auth_service.create_unverified_user(db, email, "password")
    await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (user["id"],))
    values = {capability: int(capabilities.get(capability, False)) for capability in permission_service.ALL_CAPABILITIES}
    cursor = await db.execute(
        """
        INSERT INTO account_memberships (
            user_id, account_id, manage_videos, manage_matches, manage_tags,
            manage_account_settings, manage_members, admin, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            user["id"],
            account_id,
            values[permission_service.MANAGE_VIDEOS],
            values[permission_service.MANAGE_MATCHES],
            values[permission_service.MANAGE_TAGS],
            values[permission_service.MANAGE_ACCOUNT_SETTINGS],
            values[permission_service.MANAGE_MEMBERS],
            values[permission_service.ADMIN],
        ),
    )
    await db.commit()
    session = await session_service.create_session(
        db,
        user["id"],
        active_account_id=account_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    return {
        "user": user,
        "membership": await account_service.get_membership_by_id(db, cursor.lastrowid),
        "session": session,
    }


async def _act_as(client, session: dict) -> None:
    """Replace the test client's authentication cookie."""
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, session["token"])


class TestPermissionGatedVideoUIAndMutations:
    """Video controls and mutations require manage_videos or admin."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_see_or_use_video_management_controls(self, client, db):
        """A video viewer can read videos but not see or use video mutation controls."""
        admin = await login_test_user(client, db, email="video-admin@example.com", account_name="Video Security")
        video_id = await create_test_video(client, "Restricted Video", "secure")
        viewer = await _add_limited_member(db, admin["account"]["id"], "video-viewer@example.com")
        await _act_as(client, viewer["session"])

        list_page = await client.get("/videos")
        detail = await client.get(f"/videos/{video_id}")
        upload_form = await client.get("/upload")
        edit_form = await client.get(f"/videos/{video_id}/edit")
        upload = await client.post(
            "/api/videos",
            data={"name": "Blocked"},
            files={"file": ("blocked.mp4", b"content", "video/mp4")},
        )
        edit = await client.post(f"/videos/{video_id}/edit", data={"name": "Blocked", "tags": "leak"})
        delete = await client.post(f"/videos/{video_id}/delete")
        clip = await client.post(f"/api/videos/{video_id}/clip", json={"start": 0, "end": 2})
        cut = await client.post(f"/api/videos/{video_id}/cut", json={"start": 0, "end": 2})

        assert list_page.status_code == 200
        assert detail.status_code == 200
        assert 'href="/upload"' not in list_page.text
        assert f'href="/videos/{video_id}/edit"' not in detail.text
        assert f'href="/videos/{video_id}/clip"' not in detail.text
        assert upload_form.status_code == 403
        assert edit_form.status_code == 403
        assert upload.status_code == 403
        assert edit.status_code == 403
        assert delete.status_code == 403
        assert clip.status_code == 403
        assert cut.status_code == 403


class TestPermissionGatedMatchUIAndMutations:
    """Match controls and mutations require manage_matches or admin."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_see_or_use_match_management_controls(self, client, db):
        """A match viewer can read matches but not see or use match mutation controls."""
        admin = await login_test_user(client, db, email="match-admin@example.com", account_name="Match Security")
        video_id = await create_test_video(client, "Link Target", "")
        created = await client.post("/api/matches", data={"name": "Restricted Match", "match_date": "2026-05-20"})
        match_id = int(created.headers["location"].rsplit("/", 1)[1])
        viewer = await _add_limited_member(db, admin["account"]["id"], "match-viewer@example.com")
        await _act_as(client, viewer["session"])

        list_page = await client.get("/")
        detail = await client.get(f"/matches/{match_id}")
        new_form = await client.get("/matches/new")
        edit_form = await client.get(f"/matches/{match_id}/edit")
        create = await client.post("/api/matches", data={"name": "Blocked", "match_date": "2026-05-21"})
        update = await client.post(f"/api/matches/{match_id}", data={"name": "Blocked", "match_date": "2026-05-21"})
        delete = await client.post(f"/matches/{match_id}/delete")
        link = await client.post(f"/api/matches/{match_id}/videos", data={"video_id": str(video_id)})
        unlink = await client.post(f"/api/matches/{match_id}/videos/{video_id}/remove")

        assert list_page.status_code == 200
        assert detail.status_code == 200
        assert 'href="/matches/new"' not in list_page.text
        assert f'href="/matches/{match_id}/edit"' not in detail.text
        assert f'action="/matches/{match_id}/delete"' not in detail.text
        assert 'hx-post="/api/matches/' not in detail.text
        assert new_form.status_code == 403
        assert edit_form.status_code == 403
        assert create.status_code == 403
        assert update.status_code == 403
        assert delete.status_code == 403
        assert link.status_code == 403
        assert unlink.status_code == 403


class TestPermissionGatedTagUIAndMutations:
    """Tag controls and mutations require manage_tags or admin."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_see_or_use_tag_management_controls(self, client, db):
        """A tag viewer can open settings but cannot see or submit tag controls."""
        admin = await login_test_user(client, db, email="tag-admin@example.com", account_name="Tag Security")
        await create_test_video(client, "Tagged Video", "private-tag")
        tag = await (await db.execute("SELECT id FROM tags WHERE name = ?", ("private-tag",))).fetchone()
        viewer = await _add_limited_member(db, admin["account"]["id"], "tag-viewer@example.com")
        await _act_as(client, viewer["session"])

        settings = await client.get("/settings")
        rename = await client.post(f"/api/tags/{tag['id']}/rename", data={"new_name": "blocked"})
        delete = await client.post(f"/api/tags/{tag['id']}/delete")

        assert settings.status_code == 200
        assert "private-tag" in settings.text
        assert f'action="/api/tags/{tag["id"]}/rename"' not in settings.text
        assert f'action="/api/tags/{tag["id"]}/delete"' not in settings.text
        assert rename.status_code == 403
        assert delete.status_code == 403


class TestPermissionGatedAccountInvitationAndMemberMutations:
    """Account settings, invitation, and member controls require their capabilities."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_see_or_use_account_member_invitation_controls(self, client, db):
        """A read-only member cannot edit settings, invite members, or manage memberships."""
        admin = await login_test_user(client, db, email="account-admin@example.com", account_name="Account Security")
        viewer = await _add_limited_member(db, admin["account"]["id"], "account-viewer@example.com")
        await _act_as(client, viewer["session"])

        settings = await client.get("/account/settings")
        members = await client.get("/account/members")
        update_settings = await client.post("/account/settings", data={"display_name": "Blocked"})
        invite_form = await client.get("/account/invitations/new")
        create_invite = await client.post(
            "/account/invitations",
            data={"email": "blocked-invite@example.com", "capabilities": [permission_service.MANAGE_VIDEOS]},
        )
        rights_form = await client.get(f"/account/members/{viewer['membership']['id']}/rights")
        rights_update = await client.post(f"/account/members/{viewer['membership']['id']}/rights", data={"admin": "on"})
        remove = await client.post(f"/account/members/{viewer['membership']['id']}/remove")

        assert settings.status_code == 200
        assert 'name="display_name"' not in settings.text
        assert members.status_code == 200
        assert 'data-testid="invite-member-link"' not in members.text
        assert 'data-testid="edit-member-rights"' not in members.text
        assert 'data-testid="remove-member"' not in members.text
        assert update_settings.status_code == 403
        assert invite_form.status_code == 403
        assert create_invite.status_code == 403
        assert rights_form.status_code == 403
        assert rights_update.status_code == 403
        assert remove.status_code == 403
        count = await (await db.execute("SELECT COUNT(*) AS count FROM invitations")).fetchone()
        assert count["count"] == 0


class TestRouteOrderMutationHardening:
    """Denied mutations fail before reading or changing sensitive target resources."""

    @pytest.mark.asyncio
    async def test_denied_video_and_match_mutations_do_not_leak_cross_account_existence(self, client, db):
        """Users without capabilities get 403 even for resource ids from another account."""
        await login_test_user(client, db, email="owner-a@example.com", account_name="Owner A")
        video_id = await create_test_video(client, "Other Account Video", "")
        match_resp = await client.post("/api/matches", data={"name": "Other Account Match", "match_date": "2026-05-20"})
        match_id = int(match_resp.headers["location"].rsplit("/", 1)[1])

        client.cookies.clear()
        await login_test_user(
            client,
            db,
            email="viewer-b@example.com",
            account_name="Viewer B",
            capabilities={
                permission_service.MANAGE_VIDEOS: False,
                permission_service.MANAGE_MATCHES: False,
                permission_service.ADMIN: False,
            },
        )

        assert (await client.post(f"/videos/{video_id}/edit", data={"name": "Leak", "tags": ""})).status_code == 403
        assert (await client.post(f"/videos/{video_id}/delete")).status_code == 403
        assert (await client.post(f"/api/matches/{match_id}", data={"name": "Leak", "match_date": "2026-05-21"})).status_code == 403
        assert (await client.post(f"/matches/{match_id}/delete")).status_code == 403


class TestTokenSecurityRegressions:
    """Invitation and verification tokens are hashed, expiring, and one-time use."""

    @pytest.mark.asyncio
    async def test_email_verification_tokens_are_hashed_expiring_and_one_time(self, db):
        """Verification tokens are never stored plaintext, expire, and cannot be reused."""
        user = await auth_service.create_unverified_user(db, "verify@example.com", "password")
        expired_user = await auth_service.create_unverified_user(db, "expired-verify@example.com", "password")

        token = await auth_service.create_email_verification_token(db, user["id"])
        expired_token = await auth_service.create_email_verification_token(
            db,
            expired_user["id"],
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        rows = await (await db.execute("SELECT token_hash FROM email_verification_tokens")).fetchall()
        stored_hashes = {row["token_hash"] for row in rows}
        assert token not in stored_hashes
        assert expired_token not in stored_hashes
        assert security_service.hash_token(token) in stored_hashes
        assert security_service.hash_token(expired_token) in stored_hashes

        with pytest.raises(ValueError, match="Invalid or expired verification token"):
            await auth_service.verify_email_token(db, expired_token)
        still_unverified = await auth_service.get_user_by_id(db, expired_user["id"])
        assert still_unverified["is_email_verified"] == 0

        verified = await auth_service.verify_email_token(db, token)
        assert verified["is_email_verified"] == 1
        used_row = await (
            await db.execute(
                "SELECT used_at FROM email_verification_tokens WHERE token_hash = ?",
                (security_service.hash_token(token),),
            )
        ).fetchone()
        assert used_row["used_at"] is not None

        with pytest.raises(ValueError, match="Invalid or expired verification token"):
            await auth_service.verify_email_token(db, token)

    @pytest.mark.asyncio
    async def test_invitation_tokens_are_hashed_expiring_and_one_time(self, db):
        """Invitation tokens are never stored plaintext, expire, and cannot be reused."""
        owner = await create_test_user_with_account(db, email="owner@example.com")
        invited = await auth_service.create_unverified_user(db, "invitee@example.com", "password")
        expired_invited = await auth_service.create_unverified_user(db, "expired-invitee@example.com", "password")
        await db.execute(
            "UPDATE users SET is_email_verified = 1 WHERE id IN (?, ?)",
            (invited["id"], expired_invited["id"]),
        )
        await db.commit()

        invitation = await invitation_service.create_invitation(
            db,
            account_id=owner["account"]["id"],
            invited_email="invitee@example.com",
            inviter_user_id=owner["user_id"],
        )
        expired_invitation = await invitation_service.create_invitation(
            db,
            account_id=owner["account"]["id"],
            invited_email="expired-invitee@example.com",
            inviter_user_id=owner["user_id"],
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        rows = await (await db.execute("SELECT token_hash FROM invitations")).fetchall()
        stored_hashes = {row["token_hash"] for row in rows}
        assert invitation["token"] not in stored_hashes
        assert expired_invitation["token"] not in stored_hashes
        assert security_service.hash_token(invitation["token"]) in stored_hashes
        assert security_service.hash_token(expired_invitation["token"]) in stored_hashes

        with pytest.raises(ValueError, match="expired"):
            await invitation_service.accept_invitation(db, expired_invitation["token"], expired_invited["id"])

        result = await invitation_service.accept_invitation(db, invitation["token"], invited["id"])
        assert result["status"] == "accepted"
        accepted = await invitation_service.get_invitation_by_id(db, invitation["id"])
        assert accepted["accepted_at"] is not None

        with pytest.raises(ValueError, match="already accepted"):
            await invitation_service.accept_invitation(db, invitation["token"], invited["id"])
