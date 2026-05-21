"""Account invitation services.

Invitation tokens are returned to callers once and only their SHA-256 hashes are
stored. All public service functions take the database connection first and use
simple structured dictionaries for route-friendly results.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite

from app.services import account_service, auth_service, permission_service, security_service


DEFAULT_INVITATION_TTL_DAYS = 7
INVALID_INVITATION_ERROR = "Invalid invitation"
INVITATION_REQUIRES_VERIFICATION_ERROR = "Email verification is required before accepting this invitation"


def _utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a datetime for SQLite text comparison and storage."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_datetime(value: str) -> datetime:
    """Parse SQLite timestamp text into an aware UTC datetime."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _invitation_capabilities(invitation: Mapping[str, Any]) -> dict[str, bool]:
    """Return invitation capability values as a boolean mapping."""
    return {
        capability: bool(invitation[capability])
        for capability in permission_service.ALL_CAPABILITIES
    }


async def get_invitation_by_id(db: aiosqlite.Connection, invitation_id: int) -> dict | None:
    """Return an invitation by id, or None when it does not exist."""
    cursor = await db.execute(
        """
        SELECT i.*, a.display_name AS account_display_name, u.email AS inviter_email
        FROM invitations i
        JOIN accounts a ON a.id = i.account_id
        LEFT JOIN users u ON u.id = i.inviter_user_id
        WHERE i.id = ?
        """,
        (invitation_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_invitation_by_token(db: aiosqlite.Connection, token: str) -> dict | None:
    """Return an invitation by plaintext token without changing invitation state."""
    token_hash = security_service.hash_token(token)
    cursor = await db.execute(
        """
        SELECT i.*, a.display_name AS account_display_name, u.email AS inviter_email
        FROM invitations i
        JOIN accounts a ON a.id = i.account_id
        LEFT JOIN users u ON u.id = i.inviter_user_id
        WHERE i.token_hash = ?
        """,
        (token_hash,),
    )
    row = await cursor.fetchone()
    return _invitation_with_capabilities(row) if row else None


async def get_pending_invitation_by_token(db: aiosqlite.Connection, token: str) -> dict:
    """Return a pending invitation by plaintext token or raise ValueError."""
    invitation = await get_invitation_by_token(db, token)
    _validate_invitation_is_pending(invitation)
    assert invitation is not None
    return invitation


def invitation_is_pending(invitation: Mapping[str, Any] | None) -> bool:
    """Return whether an invitation can still be accepted."""
    try:
        _validate_invitation_is_pending(dict(invitation) if invitation is not None else None)
    except ValueError:
        return False
    return True


async def create_invitation(
    db: aiosqlite.Connection,
    *,
    account_id: int,
    invited_email: str,
    inviter_user_id: int,
    capabilities: Mapping[str, Any] | None = None,
    expires_at: datetime | None = None,
) -> dict:
    """Create a pending account invitation and return invitation plus plaintext token."""
    display_email = (invited_email or "").strip()
    normalized_email = security_service.normalize_email(invited_email or "")
    if not display_email or not normalized_email:
        raise ValueError("Email is required")

    if not await permission_service.has_capability(
        db,
        inviter_user_id,
        account_id,
        permission_service.CAPABILITY_MANAGE_MEMBERS,
    ):
        raise ValueError("User must be able to manage members to create invitations")

    normalized_capabilities = permission_service.normalize_capabilities(capabilities)
    if expires_at is None:
        expires_at = _utcnow() + timedelta(days=DEFAULT_INVITATION_TTL_DAYS)

    token = security_service.create_token()
    token_hash = security_service.hash_token(token)

    try:
        cursor = await db.execute(
            """
            INSERT INTO invitations (
                account_id, invited_email, invited_normalized_email, inviter_user_id,
                manage_videos, manage_matches, manage_tags, manage_account_settings,
                manage_members, admin, token_hash, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                display_email,
                normalized_email,
                inviter_user_id,
                int(normalized_capabilities[permission_service.CAPABILITY_MANAGE_VIDEOS]),
                int(normalized_capabilities[permission_service.CAPABILITY_MANAGE_MATCHES]),
                int(normalized_capabilities[permission_service.CAPABILITY_MANAGE_TAGS]),
                int(normalized_capabilities[permission_service.CAPABILITY_MANAGE_ACCOUNT_SETTINGS]),
                int(normalized_capabilities[permission_service.CAPABILITY_MANAGE_MEMBERS]),
                int(normalized_capabilities[permission_service.CAPABILITY_ADMIN]),
                token_hash,
                _serialize_datetime(expires_at),
            ),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    invitation = await get_invitation_by_id(db, cursor.lastrowid)
    if invitation is None:  # pragma: no cover - defensive database boundary
        raise RuntimeError("Created invitation could not be loaded")
    return {**invitation, "invitation": invitation, "token": token}


async def revoke_invitation(
    db: aiosqlite.Connection,
    invitation_id: int,
    account_id: int | None = None,
    revoked_by_user_id: int | None = None,
) -> dict | bool:
    """Revoke a pending invitation and return the updated invitation."""
    if account_id is not None and revoked_by_user_id is not None:
        if not await permission_service.has_capability(
            db,
            revoked_by_user_id,
            account_id,
            permission_service.CAPABILITY_MANAGE_MEMBERS,
        ):
            raise ValueError("User must be able to manage members to revoke invitations")

    invitation = await get_invitation_by_id(db, invitation_id)
    if invitation is None or (account_id is not None and invitation["account_id"] != account_id):
        raise ValueError(INVALID_INVITATION_ERROR)
    if invitation["accepted_at"] is not None:
        raise ValueError("Invitation has already accepted")
    if invitation["revoked_at"] is not None:
        raise ValueError("Invitation has already been revoked")

    now_text = _serialize_datetime(_utcnow())
    await db.execute(
        """
        UPDATE invitations
        SET revoked_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (now_text, invitation_id),
    )
    await db.commit()
    updated = await get_invitation_by_id(db, invitation_id)
    if updated is None:  # pragma: no cover - defensive database boundary
        raise RuntimeError("Revoked invitation could not be loaded")
    return updated if revoked_by_user_id is not None else True


async def accept_invitation(
    db: aiosqlite.Connection,
    token: str,
    user_id: int | None = None,
) -> dict:
    """Accept an invitation for a matching verified user or return a safe next-step status."""
    invitation = await get_invitation_by_token(db, token)
    _validate_invitation_is_pending(invitation)
    assert invitation is not None  # narrowed by validation helper

    if user_id is None:
        existing_user = await auth_service.get_user_by_email(db, invitation["invited_normalized_email"])
        if existing_user is not None and not existing_user["is_email_verified"]:
            return _verification_required_result(invitation, existing_user)
        return _signup_required_result(invitation)

    user = await auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")
    if user["normalized_email"] != invitation["invited_normalized_email"]:
        raise ValueError("Invitation email does not match the current user")
    if not user["is_email_verified"]:
        raise ValueError(INVITATION_REQUIRES_VERIFICATION_ERROR)

    membership = await _create_or_update_membership_for_invitation(db, invitation, user_id)
    return {"status": "accepted", "invitation": invitation, "membership": membership}


def _validate_invitation_is_pending(invitation: dict | None) -> None:
    """Raise ValueError when the invitation cannot be accepted."""
    if invitation is None:
        raise ValueError(INVALID_INVITATION_ERROR)
    if invitation["accepted_at"] is not None:
        raise ValueError("Invitation has already accepted")
    if invitation["revoked_at"] is not None:
        raise ValueError("Invitation has been revoked")
    if _parse_datetime(invitation["expires_at"]) <= _utcnow():
        raise ValueError("Invitation has expired")


def _signup_required_result(invitation: Mapping[str, Any]) -> dict:
    """Return a route-friendly signup-required result for an invitation."""
    return {
        "status": "signup_required",
        "invitation": dict(invitation),
        "invitation_id": invitation["id"],
        "account_id": invitation["account_id"],
        "invited_email": invitation["invited_email"],
        "capabilities": _invitation_capabilities(invitation),
    }


def _verification_required_result(invitation: Mapping[str, Any], user: Mapping[str, Any]) -> dict:
    """Return a route-friendly verification-required result for an invitation."""
    return {
        "status": "verification_required",
        "invitation": dict(invitation),
        "user_id": user["id"],
        "account_id": invitation["account_id"],
        "invited_email": invitation["invited_email"],
        "capabilities": _invitation_capabilities(invitation),
    }


async def _create_or_update_membership_for_invitation(
    db: aiosqlite.Connection,
    invitation: Mapping[str, Any],
    user_id: int,
) -> dict:
    """Create or reactivate/update a membership using invitation capabilities."""
    capabilities = permission_service.persisted_capability_values(_invitation_capabilities(invitation))
    values = permission_service.persisted_capability_values(capabilities)
    existing = await account_service.get_membership(
        db,
        user_id,
        invitation["account_id"],
        active_only=False,
    )

    try:
        now_text = _serialize_datetime(_utcnow())
        if existing is None:
            cursor = await db.execute(
                """
                INSERT INTO account_memberships (
                    user_id, account_id, manage_videos, manage_matches, manage_tags,
                    manage_account_settings, manage_members, admin, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                _membership_values(user_id, invitation["account_id"], values),
            )
            membership_id = cursor.lastrowid
        else:
            if existing["is_active"] and existing["revoked_at"] is None:
                await permission_service.ensure_membership_can_be_updated(db, existing["id"], capabilities)
            membership_id = existing["id"]
            await db.execute(
                """
                UPDATE account_memberships
                SET manage_videos = ?, manage_matches = ?, manage_tags = ?,
                    manage_account_settings = ?, manage_members = ?, admin = ?,
                    is_active = 1, revoked_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    values[permission_service.CAPABILITY_MANAGE_VIDEOS],
                    values[permission_service.CAPABILITY_MANAGE_MATCHES],
                    values[permission_service.CAPABILITY_MANAGE_TAGS],
                    values[permission_service.CAPABILITY_MANAGE_ACCOUNT_SETTINGS],
                    values[permission_service.CAPABILITY_MANAGE_MEMBERS],
                    values[permission_service.CAPABILITY_ADMIN],
                    membership_id,
                ),
            )

        await db.execute(
            """
            UPDATE invitations
            SET accepted_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (now_text, invitation["id"]),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    membership = await account_service.get_membership(
        db,
        user_id,
        invitation["account_id"],
        active_only=False,
    )
    if membership is None:  # pragma: no cover - defensive database boundary
        raise RuntimeError("Accepted membership could not be loaded")
    return membership


def _membership_values(user_id: int, account_id: int, values: Mapping[str, int]) -> tuple:
    """Return INSERT values for an invitation-created membership."""
    return (
        user_id,
        account_id,
        values[permission_service.CAPABILITY_MANAGE_VIDEOS],
        values[permission_service.CAPABILITY_MANAGE_MATCHES],
        values[permission_service.CAPABILITY_MANAGE_TAGS],
        values[permission_service.CAPABILITY_MANAGE_ACCOUNT_SETTINGS],
        values[permission_service.CAPABILITY_MANAGE_MEMBERS],
        values[permission_service.CAPABILITY_ADMIN],
    )


def _invitation_with_capabilities(row) -> dict:
    invitation = dict(row)
    invitation["capabilities"] = _invitation_capabilities(invitation)
    return invitation
