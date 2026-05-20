"""Tests for authentication FastAPI dependency helpers."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.dependencies import (
    AUTH_SESSION_COOKIE,
    get_current_user_optional,
    require_active_account,
    require_current_user,
)
from app.services import account_service, security_service, session_service


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_with_cookie(token: str | None = None) -> Request:
    headers = Headers({"cookie": f"{AUTH_SESSION_COOKIE}={token}"} if token else {})
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers.raw})


async def _create_user(db, email: str = "user@example.com") -> int:
    cursor = await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, 1)
        """,
        (email, email.strip().lower(), security_service.hash_password("password")),
    )
    await db.commit()
    return cursor.lastrowid


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_without_cookie(db):
    assert await get_current_user_optional(_request_with_cookie(), db) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_loads_live_session_user(db):
    user_id = await _create_user(db)
    created = await session_service.create_session(
        db,
        user_id=user_id,
        expires_at=_utc_now() + timedelta(days=1),
    )

    current_user = await get_current_user_optional(_request_with_cookie(created["token"]), db)

    assert current_user is not None
    assert current_user["id"] == user_id
    assert current_user["user"]["id"] == user_id
    assert current_user["session"]["id"] == created["id"]
    assert "password_hash" not in current_user
    assert "password_hash" not in current_user["user"]
    assert "token_hash" not in current_user["session"]


@pytest.mark.asyncio
async def test_get_current_user_optional_rejects_revoked_and_expired_sessions(db):
    user_id = await _create_user(db)
    revoked = await session_service.create_session(
        db,
        user_id=user_id,
        expires_at=_utc_now() + timedelta(days=1),
    )
    expired = await session_service.create_session(
        db,
        user_id=user_id,
        expires_at=_utc_now() - timedelta(seconds=1),
    )
    await session_service.revoke_session(db, revoked["token"])

    assert await get_current_user_optional(_request_with_cookie(revoked["token"]), db) is None
    assert await get_current_user_optional(_request_with_cookie(expired["token"]), db) is None


@pytest.mark.asyncio
async def test_require_current_user_redirects_anonymous_users_to_login(db):
    with pytest.raises(HTTPException) as exc_info:
        await require_current_user(_request_with_cookie(), db)

    assert exc_info.value.status_code == 303
    assert exc_info.value.headers == {"Location": "/login"}


@pytest.mark.asyncio
async def test_require_active_account_resolves_current_membership(db):
    user_id = await _create_user(db)
    created_account = await account_service.create_account_with_admin_membership(db, user_id, "Team")
    session = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=created_account["account"]["id"],
        expires_at=_utc_now() + timedelta(days=1),
    )

    context = await require_active_account(_request_with_cookie(session["token"]), db)

    assert context["user"]["id"] == user_id
    assert context["session"]["id"] == session["id"]
    assert context["account"]["id"] == created_account["account"]["id"]
    assert context["membership"]["id"] == created_account["membership"]["id"]


@pytest.mark.asyncio
async def test_require_active_account_ignores_revoked_active_membership_and_uses_live_one(db):
    user_id = await _create_user(db)
    revoked = await account_service.create_account_with_admin_membership(db, user_id, "Revoked")
    live = await account_service.create_account_with_admin_membership(db, user_id, "Live")
    await db.execute(
        "UPDATE account_memberships SET is_active = 0, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
        (revoked["membership"]["id"],),
    )
    await db.commit()
    session = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=revoked["account"]["id"],
        expires_at=_utc_now() + timedelta(days=1),
    )

    context = await require_active_account(_request_with_cookie(session["token"]), db)

    assert context["account"]["id"] == live["account"]["id"]
    assert context["membership"]["id"] == live["membership"]["id"]
    assert await account_service.get_session_active_account_id(db, session["id"]) == live["account"]["id"]


@pytest.mark.asyncio
async def test_require_active_account_rejects_user_without_active_membership(db):
    user_id = await _create_user(db)
    session = await session_service.create_session(
        db,
        user_id=user_id,
        expires_at=_utc_now() + timedelta(days=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_active_account(_request_with_cookie(session["token"]), db)

    assert exc_info.value.status_code == 403
