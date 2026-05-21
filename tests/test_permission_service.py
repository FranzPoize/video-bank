"""
Tests for account membership and permission helpers.

Run with: pytest tests/test_permission_service.py -v
"""

import pytest

from app.services import permission_service


async def _create_user(db, email: str) -> int:
    await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, 1)
        """,
        (email, email.lower(), "test-password-hash"),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT id FROM users WHERE normalized_email = ?",
        (email.lower(),),
    )
    row = await cursor.fetchone()
    return row["id"]


async def _create_account(db, display_name: str = "Team Account") -> int:
    await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        (display_name,),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT id FROM accounts WHERE display_name = ?",
        (display_name,),
    )
    row = await cursor.fetchone()
    return row["id"]


async def _create_membership(db, user_id: int, account_id: int, **capabilities) -> int:
    values = {capability: int(capabilities.get(capability, False)) for capability in permission_service.ALL_CAPABILITIES}
    await db.execute(
        """
        INSERT INTO account_memberships (
            user_id, account_id, manage_videos, manage_matches, manage_tags,
            manage_account_settings, manage_members, admin
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            account_id,
            values[permission_service.CAPABILITY_MANAGE_VIDEOS],
            values[permission_service.CAPABILITY_MANAGE_MATCHES],
            values[permission_service.CAPABILITY_MANAGE_TAGS],
            values[permission_service.CAPABILITY_MANAGE_ACCOUNT_SETTINGS],
            values[permission_service.CAPABILITY_MANAGE_MEMBERS],
            values[permission_service.CAPABILITY_ADMIN],
        ),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT id FROM account_memberships WHERE user_id = ? AND account_id = ?",
        (user_id, account_id),
    )
    row = await cursor.fetchone()
    return row["id"]


class TestPermissionConstants:
    def test_defines_expected_capability_constants_and_presets(self):
        assert permission_service.ALL_CAPABILITIES == (
            "manage_videos",
            "manage_matches",
            "manage_tags",
            "manage_account_settings",
            "manage_members",
            "admin",
        )

        assert permission_service.DEFAULT_CAPABILITY_PRESETS["admin"]["admin"] is True
        assert permission_service.DEFAULT_CAPABILITY_PRESETS["viewer"] == {
            capability: False for capability in permission_service.ALL_CAPABILITIES
        }


class TestMembershipChecks:
    async def test_get_active_membership_returns_member(self, db):
        user_id = await _create_user(db, "member@example.com")
        account_id = await _create_account(db)
        await _create_membership(db, user_id, account_id, manage_videos=True)

        membership = await permission_service.get_active_membership(db, user_id, account_id)

        assert membership is not None
        assert membership["user_id"] == user_id
        assert membership["account_id"] == account_id

    async def test_get_active_membership_rejects_non_member(self, db):
        user_id = await _create_user(db, "outsider@example.com")
        account_id = await _create_account(db)

        membership = await permission_service.get_active_membership(db, user_id, account_id)

        assert membership is None
        assert await permission_service.is_account_member(db, user_id, account_id) is False

    async def test_revoked_membership_is_not_active(self, db):
        user_id = await _create_user(db, "revoked@example.com")
        account_id = await _create_account(db)
        membership_id = await _create_membership(db, user_id, account_id, admin=True)
        await db.execute(
            "UPDATE account_memberships SET is_active = 0, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
            (membership_id,),
        )
        await db.commit()

        assert await permission_service.get_active_membership(db, user_id, account_id) is None


class TestCapabilityChecks:
    async def test_explicit_capability_allows_member(self, db):
        user_id = await _create_user(db, "video-manager@example.com")
        account_id = await _create_account(db)
        await _create_membership(db, user_id, account_id, manage_videos=True)

        assert await permission_service.has_capability(
            db, user_id, account_id, permission_service.CAPABILITY_MANAGE_VIDEOS
        ) is True
        assert await permission_service.has_capability(
            db, user_id, account_id, permission_service.CAPABILITY_MANAGE_TAGS
        ) is False

    async def test_admin_grants_all_capabilities(self, db):
        user_id = await _create_user(db, "admin@example.com")
        account_id = await _create_account(db)
        await _create_membership(db, user_id, account_id, admin=True)

        for capability in permission_service.ALL_CAPABILITIES:
            assert await permission_service.has_capability(db, user_id, account_id, capability) is True

    async def test_non_member_has_no_capabilities(self, db):
        user_id = await _create_user(db, "non-member@example.com")
        account_id = await _create_account(db)

        assert await permission_service.has_capability(
            db, user_id, account_id, permission_service.CAPABILITY_MANAGE_MEMBERS
        ) is False
        with pytest.raises(ValueError, match="Account membership is required"):
            await permission_service.require_capability(
                db, user_id, account_id, permission_service.CAPABILITY_MANAGE_MEMBERS
            )

    async def test_get_current_capabilities_expands_admin_to_all_capabilities(self, db):
        user_id = await _create_user(db, "admin-capabilities@example.com")
        account_id = await _create_account(db)
        await _create_membership(db, user_id, account_id, admin=True)

        capabilities = await permission_service.get_current_capabilities(db, user_id, account_id)

        assert capabilities == {capability: True for capability in permission_service.ALL_CAPABILITIES}

    async def test_get_current_capabilities_returns_none_for_non_member(self, db):
        user_id = await _create_user(db, "missing-capabilities@example.com")
        account_id = await _create_account(db)

        assert await permission_service.get_current_capabilities(db, user_id, account_id) is None

    async def test_can_manage_account_settings_helper_allows_capability_or_admin(self, db):
        settings_user_id = await _create_user(db, "settings-helper@example.com")
        admin_user_id = await _create_user(db, "settings-admin-helper@example.com")
        viewer_user_id = await _create_user(db, "settings-viewer@example.com")
        account_id = await _create_account(db)
        await _create_membership(
            db,
            settings_user_id,
            account_id,
            manage_account_settings=True,
        )
        await _create_membership(db, admin_user_id, account_id, admin=True)
        await _create_membership(db, viewer_user_id, account_id)

        assert await permission_service.can_manage_account_settings(db, settings_user_id, account_id) is True
        assert await permission_service.can_manage_account_settings(db, admin_user_id, account_id) is True
        assert await permission_service.can_manage_account_settings(db, viewer_user_id, account_id) is False


class TestLastAdminProtection:
    async def test_cannot_remove_only_administrator(self, db):
        user_id = await _create_user(db, "sole-admin@example.com")
        account_id = await _create_account(db)
        membership_id = await _create_membership(db, user_id, account_id, admin=True)

        with pytest.raises(ValueError, match="Cannot remove the only administrator"):
            await permission_service.ensure_membership_can_be_removed(db, membership_id)

    async def test_can_remove_admin_when_another_admin_remains(self, db):
        account_id = await _create_account(db)
        first_user_id = await _create_user(db, "first-admin@example.com")
        second_user_id = await _create_user(db, "second-admin@example.com")
        membership_id = await _create_membership(db, first_user_id, account_id, admin=True)
        await _create_membership(db, second_user_id, account_id, admin=True)

        assert await permission_service.ensure_membership_can_be_removed(db, membership_id) is True

    async def test_cannot_demote_only_administrator(self, db):
        user_id = await _create_user(db, "demote-admin@example.com")
        account_id = await _create_account(db)
        membership_id = await _create_membership(db, user_id, account_id, admin=True)

        with pytest.raises(ValueError, match="Cannot demote the only administrator"):
            await permission_service.ensure_membership_can_be_updated(
                db,
                membership_id,
                {permission_service.CAPABILITY_ADMIN: False},
            )

    async def test_can_update_non_admin_capabilities_for_only_administrator(self, db):
        user_id = await _create_user(db, "settings-admin@example.com")
        account_id = await _create_account(db)
        membership_id = await _create_membership(db, user_id, account_id, admin=True)

        assert await permission_service.ensure_membership_can_be_updated(
            db,
            membership_id,
            {permission_service.CAPABILITY_ADMIN: True, permission_service.CAPABILITY_MANAGE_TAGS: False},
        ) is True
