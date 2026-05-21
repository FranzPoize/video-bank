"""Route and UI tests for account switching, settings, and members."""

import pytest

from app.dependencies import SESSION_COOKIE_NAME
from app.services import account_service, auth_service, security_service, session_service
from tests.conftest import create_test_user_with_account, login_test_user


class TestAccountSwitcherRoutes:
    """Tests for account switcher rendering and switching behavior."""

    @pytest.mark.asyncio
    async def test_one_account_does_not_render_switcher(self, client, db):
        """A user with one account sees account context but no switcher form."""
        await login_test_user(client, db, email="solo@example.com", account_name="Solo Team")

        response = await client.get("/account/settings")

        assert response.status_code == 200
        assert "Solo Team" in response.text
        assert 'data-testid="account-switcher"' not in response.text

    @pytest.mark.asyncio
    async def test_multiple_accounts_can_switch_active_membership(self, client, db):
        """A multi-account user can switch only to an account they belong to."""
        context = await login_test_user(client, db, email="multi@example.com", account_name="First Team")
        second = await account_service.create_account_with_admin_membership(db, context["user_id"], "Second Team")

        page = await client.get("/account/settings")
        assert page.status_code == 200
        assert 'data-testid="account-switcher"' in page.text
        assert "First Team" in page.text
        assert "Second Team" in page.text

        response = await client.post(
            "/accounts/switch",
            data={"account_id": str(second["account"]["id"]), "next": "/account/settings"},
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/account/settings"
        session = await session_service.load_session(db, context["session"]["token"])
        assert session["active_account_id"] == second["account"]["id"]

    @pytest.mark.asyncio
    async def test_forged_account_switch_target_is_rejected(self, client, db):
        """Posting an account id without active membership is rejected."""
        context = await login_test_user(client, db, email="owner@example.com", account_name="Owner Team")
        other = await create_test_user_with_account(db, email="other@example.com", account_name="Other Team")

        response = await client.post(
            "/accounts/switch",
            data={"account_id": str(other["account"]["id"]), "next": "/account/settings"},
        )

        assert response.status_code == 403
        session = await session_service.load_session(db, context["session"]["token"])
        assert session["active_account_id"] == context["account"]["id"]


class TestAccountSettingsRoutes:
    """Tests for account settings display and permission-gated edits."""

    @pytest.mark.asyncio
    async def test_account_setting_edits_require_capability(self, client, db):
        """Display name edits require manage_account_settings or admin."""
        await login_test_user(
            client,
            db,
            email="viewer@example.com",
            account_name="Viewer Team",
            capabilities={"manage_account_settings": False, "admin": False},
        )

        denied = await client.post("/account/settings", data={"display_name": "Denied Team"})
        assert denied.status_code == 403
        account = (await account_service.list_accounts_for_user(db, 1))[0]
        assert account["display_name"] == "Viewer Team"

        client.cookies.clear()
        manager = await login_test_user(
            client,
            db,
            email="manager@example.com",
            account_name="Managed Team",
            capabilities={"manage_account_settings": True, "admin": False},
        )

        allowed = await client.post("/account/settings", data={"display_name": "Renamed Team"})
        assert allowed.status_code == 303
        updated = await account_service.get_account(db, manager["account"]["id"])
        assert updated["display_name"] == "Renamed Team"

    @pytest.mark.asyncio
    async def test_settings_page_hides_edit_controls_without_capability(self, client, db):
        """Non-admin members can see account context but not restricted edit controls."""
        await login_test_user(
            client,
            db,
            email="member@example.com",
            account_name="Read Only Team",
            capabilities={"manage_account_settings": False, "admin": False},
        )

        response = await client.get("/account/settings")

        assert response.status_code == 200
        assert "Read Only Team" in response.text
        assert 'name="display_name"' not in response.text
        assert "You can view this account, but you cannot edit account settings." in response.text


class TestAccountMembersRoutes:
    """Tests for account member list authorization and controls."""

    @pytest.mark.asyncio
    async def test_member_list_requires_membership(self, client, db):
        """Users without an active account membership cannot view member lists."""
        cursor = await db.execute(
            """
            INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
            VALUES (?, ?, ?, 1)
            """,
            ("nomember@example.com", "nomember@example.com", security_service.hash_password("password")),
        )
        await db.commit()
        session = await session_service.create_session(db, cursor.lastrowid, active_account_id=None)
        client.cookies.set(SESSION_COOKIE_NAME, session["token"])

        response = await client.get("/account/members")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_member_list_hides_and_shows_controls_by_capability(self, client, db):
        """Member list is visible to members and management controls are gated."""
        readonly = await login_test_user(
            client,
            db,
            email="readonly@example.com",
            account_name="Members Team",
            capabilities={"manage_members": False, "admin": False},
        )

        hidden = await client.get("/account/members")
        assert hidden.status_code == 200
        assert "readonly@example.com" in hidden.text
        assert 'data-testid="member-management-controls"' not in hidden.text

        client.cookies.clear()
        admin_user = await auth_service.create_unverified_user(db, "admin@example.com", "password")
        await db.execute("UPDATE users SET is_email_verified = 1 WHERE id = ?", (admin_user["id"],))
        await account_service.create_first_admin_membership(db, admin_user["id"], readonly["account"]["id"])
        admin_session = await session_service.create_session(
            db,
            admin_user["id"],
            active_account_id=readonly["account"]["id"],
        )
        client.cookies.set(SESSION_COOKIE_NAME, admin_session["token"])

        shown = await client.get("/account/members")
        assert shown.status_code == 200
        assert "readonly@example.com" in shown.text
        assert "admin@example.com" in shown.text
        assert 'data-testid="member-management-controls"' in shown.text
