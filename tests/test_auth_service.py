"""
Tests for authentication user and email verification services.

Run with: pytest tests/test_auth_service.py -v
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import auth_service, security_service


pytestmark = pytest.mark.asyncio


async def test_create_unverified_user_hashes_password_and_normalizes_email(db):
    user = await auth_service.create_unverified_user(
        db,
        "  Person+Signup@Example.COM  ",
        "correct horse battery staple",
    )

    assert user["id"] > 0
    assert user["email"] == "Person+Signup@Example.COM"
    assert user["normalized_email"] == "person+signup@example.com"
    assert user["is_email_verified"] == 0
    assert user["password_hash"] != "correct horse battery staple"
    assert security_service.verify_password(
        "correct horse battery staple",
        user["password_hash"],
    )


async def test_duplicate_signup_rejected_with_safe_generic_error(db):
    await auth_service.create_unverified_user(db, "User@Example.com", "password-one")

    with pytest.raises(ValueError) as exc_info:
        await auth_service.create_unverified_user(db, " user@example.COM ", "password-two")

    assert str(exc_info.value) == "Unable to create account with these details"


async def test_validate_login_rejects_unknown_and_wrong_password_generically(db):
    await auth_service.create_unverified_user(db, "user@example.com", "correct-password")
    await db.execute(
        "UPDATE users SET is_email_verified = 1, email_verified_at = CURRENT_TIMESTAMP WHERE normalized_email = ?",
        ("user@example.com",),
    )
    await db.commit()

    with pytest.raises(ValueError) as unknown_exc:
        await auth_service.validate_login_credentials(db, "missing@example.com", "anything")
    with pytest.raises(ValueError) as wrong_exc:
        await auth_service.validate_login_credentials(db, "user@example.com", "wrong-password")

    assert str(unknown_exc.value) == "Invalid email or password"
    assert str(wrong_exc.value) == "Invalid email or password"


async def test_validate_login_rejects_unverified_user(db):
    await auth_service.create_unverified_user(db, "user@example.com", "correct-password")

    with pytest.raises(ValueError) as exc_info:
        await auth_service.validate_login_credentials(db, "USER@example.com", "correct-password")

    assert str(exc_info.value) == "Email address is not verified"


async def test_validate_login_returns_verified_user(db):
    created = await auth_service.create_unverified_user(db, "user@example.com", "correct-password")
    await db.execute(
        "UPDATE users SET is_email_verified = 1, email_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
        (created["id"],),
    )
    await db.commit()

    user = await auth_service.validate_login_credentials(db, "USER@example.com", "correct-password")

    assert user["id"] == created["id"]
    assert user["normalized_email"] == "user@example.com"


async def test_email_verification_token_is_stored_hashed(db):
    user = await auth_service.create_unverified_user(db, "user@example.com", "password")

    token = await auth_service.create_email_verification_token(db, user["id"])

    row = await (await db.execute("SELECT token_hash FROM email_verification_tokens")).fetchone()
    assert row["token_hash"] != token
    assert row["token_hash"] == security_service.hash_token(token)


async def test_verify_email_token_expires_and_does_not_verify_user(db):
    user = await auth_service.create_unverified_user(db, "user@example.com", "password")
    token = await auth_service.create_email_verification_token(
        db,
        user["id"],
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    with pytest.raises(ValueError) as exc_info:
        await auth_service.verify_email_token(db, token)

    assert str(exc_info.value) == "Invalid or expired verification token"
    stored_user = await auth_service.get_user_by_id(db, user["id"])
    assert stored_user["is_email_verified"] == 0


async def test_verify_email_token_is_one_time_use(db):
    user = await auth_service.create_unverified_user(db, "user@example.com", "password")
    token = await auth_service.create_email_verification_token(db, user["id"])

    verified = await auth_service.verify_email_token(db, token)

    assert verified["is_email_verified"] == 1
    with pytest.raises(ValueError) as exc_info:
        await auth_service.verify_email_token(db, token)
    assert str(exc_info.value) == "Invalid or expired verification token"


async def test_signup_verification_creates_account_and_admin_membership(db):
    user = await auth_service.create_unverified_user(db, "owner@example.com", "password")
    token = await auth_service.create_email_verification_token(db, user["id"])

    verified = await auth_service.verify_email_token(
        db,
        token,
        create_account=True,
        account_display_name="Owner Account",
    )

    account = await (await db.execute("SELECT * FROM accounts")).fetchone()
    membership = await (
        await db.execute(
            "SELECT * FROM account_memberships WHERE user_id = ? AND account_id = ?",
            (user["id"], account["id"]),
        )
    ).fetchone()

    assert verified["is_email_verified"] == 1
    assert account["display_name"] == "Owner Account"
    assert membership["admin"] == 1
    assert membership["manage_videos"] == 1
    assert membership["manage_matches"] == 1
    assert membership["manage_tags"] == 1
    assert membership["manage_account_settings"] == 1
    assert membership["manage_members"] == 1
