"""Route tests for editing and removing account members."""

import pytest

from app.dependencies import SESSION_COOKIE_NAME
from app.services import account_service, auth_service, permission_service, session_service
from tests.conftest import login_test_user


async def _add_member(db, account_id: int, email: str, **capabilities) -> dict:
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
    return {"user": user, "membership": await account_service.get_membership_by_id(db, cursor.lastrowid)}


class TestMemberRightsRoutes:
    @pytest.mark.asyncio
    async def test_rights_editor_updates_capabilities(self, client, db):
        """A member manager can open the editor and save selected rights."""
        admin = await login_test_user(client, db, email="admin-rights@example.com", account_name="Rights Team")
        member = await _add_member(db, admin["account"]["id"], "member-rights@example.com")

        editor = await client.get(f"/account/members/{member['membership']['id']}/rights")

        assert editor.status_code == 200
        assert "member-rights@example.com" in editor.text
        assert 'data-testid="member-rights-form"' in editor.text

        saved = await client.post(
            f"/account/members/{member['membership']['id']}/rights",
            data={"manage_videos": "on", "manage_tags": "on", "manage_members": "on"},
        )

        assert saved.status_code == 303
        assert saved.headers["location"] == "/account/members"
        updated = await account_service.get_membership_by_id(db, member["membership"]["id"])
        assert updated[permission_service.MANAGE_VIDEOS] == 1
        assert updated[permission_service.MANAGE_TAGS] == 1
        assert updated[permission_service.MANAGE_MEMBERS] == 1
        assert updated[permission_service.MANAGE_MATCHES] == 0
        assert updated[permission_service.ADMIN] == 0

    @pytest.mark.asyncio
    async def test_demoting_last_admin_is_rejected(self, client, db):
        """The only account admin cannot remove their own admin right."""
        admin = await login_test_user(client, db, email="only-admin@example.com", account_name="Only Admin Team")

        response = await client.post(
            f"/account/members/{admin['membership']['id']}/rights",
            data={"manage_videos": "on", "manage_members": "on"},
        )

        assert response.status_code == 400
        assert "Cannot demote the only administrator" in response.text
        unchanged = await account_service.get_membership_by_id(db, admin["membership"]["id"])
        assert unchanged[permission_service.ADMIN] == 1

    @pytest.mark.asyncio
    async def test_non_manager_cannot_edit_rights(self, client, db):
        """Members without manage_members are forbidden from editing rights."""
        viewer = await login_test_user(
            client,
            db,
            email="viewer-manager@example.com",
            account_name="Forbidden Team",
            capabilities={"manage_members": False, "admin": False},
        )
        target = await _add_member(db, viewer["account"]["id"], "target-forbidden@example.com")

        get_response = await client.get(f"/account/members/{target['membership']['id']}/rights")
        post_response = await client.post(
            f"/account/members/{target['membership']['id']}/rights",
            data={"admin": "on"},
        )

        assert get_response.status_code == 403
        assert post_response.status_code == 403
        unchanged = await account_service.get_membership_by_id(db, target["membership"]["id"])
        assert unchanged[permission_service.ADMIN] == 0


class TestMemberRemoveRoutes:
    @pytest.mark.asyncio
    async def test_member_manager_can_remove_non_last_admin(self, client, db):
        """Removing a regular member revokes their active membership."""
        admin = await login_test_user(client, db, email="admin-remove@example.com", account_name="Remove Team")
        member = await _add_member(db, admin["account"]["id"], "remove-me@example.com", manage_videos=True)

        response = await client.post(f"/account/members/{member['membership']['id']}/remove")

        assert response.status_code == 303
        assert response.headers["location"] == "/account/members"
        removed = await account_service.get_membership_by_id(db, member["membership"]["id"])
        assert removed["is_active"] == 0
        assert removed["revoked_at"] is not None

    @pytest.mark.asyncio
    async def test_removing_last_admin_is_rejected(self, client, db):
        """The only account admin cannot remove themselves."""
        admin = await login_test_user(client, db, email="last-remove@example.com", account_name="Last Admin Team")

        response = await client.post(f"/account/members/{admin['membership']['id']}/remove")

        assert response.status_code == 400
        assert "Cannot remove the only administrator" in response.text
        unchanged = await account_service.get_membership_by_id(db, admin["membership"]["id"])
        assert unchanged["is_active"] == 1

    @pytest.mark.asyncio
    async def test_non_manager_cannot_remove_member(self, client, db):
        """Members without manage_members are forbidden from removing members."""
        viewer = await login_test_user(
            client,
            db,
            email="viewer-remove@example.com",
            account_name="No Remove Team",
            capabilities={"manage_members": False, "admin": False},
        )
        target = await _add_member(db, viewer["account"]["id"], "target-remove@example.com")

        response = await client.post(f"/account/members/{target['membership']['id']}/remove")

        assert response.status_code == 403
        unchanged = await account_service.get_membership_by_id(db, target["membership"]["id"])
        assert unchanged["is_active"] == 1


class TestMemberControls:
    @pytest.mark.asyncio
    async def test_controls_are_gated_on_member_list(self, client, db):
        """Managers see edit/remove controls while viewers do not."""
        viewer = await login_test_user(
            client,
            db,
            email="controls-viewer@example.com",
            account_name="Controls Team",
            capabilities={"manage_members": False, "admin": False},
        )
        await _add_member(db, viewer["account"]["id"], "controls-target@example.com")

        hidden = await client.get("/account/members")
        assert hidden.status_code == 200
        assert 'data-testid="edit-member-rights"' not in hidden.text
        assert 'data-testid="remove-member"' not in hidden.text

        client.cookies.clear()
        admin_user = await _add_member(db, viewer["account"]["id"], "controls-admin@example.com", admin=True)
        admin_session = await session_service.create_session(
            db,
            admin_user["user"]["id"],
            active_account_id=viewer["account"]["id"],
        )
        client.cookies.set(SESSION_COOKIE_NAME, admin_session["token"])

        shown = await client.get("/account/members")
        assert shown.status_code == 200
        assert 'data-testid="edit-member-rights"' in shown.text
        assert 'data-testid="remove-member"' in shown.text
