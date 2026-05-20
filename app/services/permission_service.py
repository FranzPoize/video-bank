"""
Account membership and capability checks.

All service functions take the database connection as the first argument. The
``admin`` capability is persisted like every other capability and grants every
authorization decision for an active account member.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CAPABILITY_MANAGE_VIDEOS = "manage_videos"
CAPABILITY_MANAGE_MATCHES = "manage_matches"
CAPABILITY_MANAGE_TAGS = "manage_tags"
CAPABILITY_MANAGE_ACCOUNT_SETTINGS = "manage_account_settings"
CAPABILITY_MANAGE_MEMBERS = "manage_members"
CAPABILITY_ADMIN = "admin"

# Short aliases are convenient for route code while keeping explicit constants
# available for tests and callers that prefer the longer names.
MANAGE_VIDEOS = CAPABILITY_MANAGE_VIDEOS
MANAGE_MATCHES = CAPABILITY_MANAGE_MATCHES
MANAGE_TAGS = CAPABILITY_MANAGE_TAGS
MANAGE_ACCOUNT_SETTINGS = CAPABILITY_MANAGE_ACCOUNT_SETTINGS
MANAGE_MEMBERS = CAPABILITY_MANAGE_MEMBERS
ADMIN = CAPABILITY_ADMIN

ALL_CAPABILITIES = (
    CAPABILITY_MANAGE_VIDEOS,
    CAPABILITY_MANAGE_MATCHES,
    CAPABILITY_MANAGE_TAGS,
    CAPABILITY_MANAGE_ACCOUNT_SETTINGS,
    CAPABILITY_MANAGE_MEMBERS,
    CAPABILITY_ADMIN,
)

DEFAULT_CAPABILITY_PRESETS = {
    "viewer": {capability: False for capability in ALL_CAPABILITIES},
    "video_manager": {
        CAPABILITY_MANAGE_VIDEOS: True,
        CAPABILITY_MANAGE_MATCHES: False,
        CAPABILITY_MANAGE_TAGS: True,
        CAPABILITY_MANAGE_ACCOUNT_SETTINGS: False,
        CAPABILITY_MANAGE_MEMBERS: False,
        CAPABILITY_ADMIN: False,
    },
    "match_manager": {
        CAPABILITY_MANAGE_VIDEOS: False,
        CAPABILITY_MANAGE_MATCHES: True,
        CAPABILITY_MANAGE_TAGS: False,
        CAPABILITY_MANAGE_ACCOUNT_SETTINGS: False,
        CAPABILITY_MANAGE_MEMBERS: False,
        CAPABILITY_ADMIN: False,
    },
    "account_manager": {
        CAPABILITY_MANAGE_VIDEOS: False,
        CAPABILITY_MANAGE_MATCHES: False,
        CAPABILITY_MANAGE_TAGS: False,
        CAPABILITY_MANAGE_ACCOUNT_SETTINGS: True,
        CAPABILITY_MANAGE_MEMBERS: True,
        CAPABILITY_ADMIN: False,
    },
    "admin": {capability: True for capability in ALL_CAPABILITIES},
}


def _validate_capability(capability: str) -> str:
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability}")
    return capability


def normalize_capabilities(capabilities: Mapping[str, Any] | None = None, **overrides: Any) -> dict[str, bool]:
    """Return a complete boolean capability mapping.

    Missing capabilities default to ``False``. Unknown capability keys are
    rejected so callers cannot silently persist unsupported flags.
    """
    normalized = {capability: False for capability in ALL_CAPABILITIES}
    supplied = dict(capabilities or {})
    supplied.update(overrides)

    for capability, value in supplied.items():
        _validate_capability(capability)
        normalized[capability] = bool(value)

    return normalized


def _normalize_capability_overrides(capabilities: Mapping[str, Any] | None = None) -> dict[str, bool]:
    """Return provided capability keys as booleans without defaulting missing keys."""
    normalized = {}
    for capability, value in dict(capabilities or {}).items():
        _validate_capability(capability)
        normalized[capability] = bool(value)
    return normalized


async def get_active_membership(db, user_id: int, account_id: int):
    """Return the active membership row for a user/account pair, or ``None``."""
    cursor = await db.execute(
        """
        SELECT *
        FROM account_memberships
        WHERE user_id = ?
          AND account_id = ?
          AND is_active = 1
          AND revoked_at IS NULL
        """,
        (user_id, account_id),
    )
    return await cursor.fetchone()


async def get_membership_by_id(db, membership_id: int):
    """Return an active membership by id, or ``None``."""
    cursor = await db.execute(
        """
        SELECT *
        FROM account_memberships
        WHERE id = ?
          AND is_active = 1
          AND revoked_at IS NULL
        """,
        (membership_id,),
    )
    return await cursor.fetchone()


async def is_account_member(db, user_id: int, account_id: int) -> bool:
    """Return whether the user has an active membership in the account."""
    return await get_active_membership(db, user_id, account_id) is not None


async def require_account_membership(db, user_id: int, account_id: int):
    """Return the active membership or raise ``ValueError``."""
    membership = await get_active_membership(db, user_id, account_id)
    if membership is None:
        raise ValueError("Account membership is required")
    return membership


async def has_capability(db, user_id: int, account_id: int, capability: str) -> bool:
    """Return whether an active account member has a capability.

    Admin grants every capability. Non-members are rejected by returning
    ``False`` rather than leaking account existence through an exception.
    """
    capability = _validate_capability(capability)
    membership = await get_active_membership(db, user_id, account_id)
    if membership is None:
        return False
    if bool(membership[CAPABILITY_ADMIN]):
        return True
    return bool(membership[capability])


async def require_capability(db, user_id: int, account_id: int, capability: str):
    """Return the active membership if it has ``capability``; otherwise raise."""
    capability = _validate_capability(capability)
    membership = await require_account_membership(db, user_id, account_id)
    if bool(membership[CAPABILITY_ADMIN]) or bool(membership[capability]):
        return membership
    raise ValueError(f"Capability required: {capability}")


async def count_active_admins(db, account_id: int) -> int:
    """Count active administrators for an account."""
    cursor = await db.execute(
        """
        SELECT COUNT(*) AS admin_count
        FROM account_memberships
        WHERE account_id = ?
          AND admin = 1
          AND is_active = 1
          AND revoked_at IS NULL
        """,
        (account_id,),
    )
    row = await cursor.fetchone()
    return int(row["admin_count"])


async def ensure_membership_can_be_removed(db, membership_id: int) -> bool:
    """Raise if removing this membership would remove the account's only admin."""
    membership = await get_membership_by_id(db, membership_id)
    if membership is None:
        raise ValueError("Active membership not found")

    if bool(membership[CAPABILITY_ADMIN]) and await count_active_admins(db, membership["account_id"]) <= 1:
        raise ValueError("Cannot remove the only administrator")

    return True


async def ensure_membership_can_be_updated(
    db,
    membership_id: int,
    capabilities: Mapping[str, Any],
) -> bool:
    """Raise if a capability update would demote the account's only admin."""
    membership = await get_membership_by_id(db, membership_id)
    if membership is None:
        raise ValueError("Active membership not found")

    normalized = normalize_capabilities({capability: membership[capability] for capability in ALL_CAPABILITIES})
    normalized.update(_normalize_capability_overrides(capabilities))

    if (
        bool(membership[CAPABILITY_ADMIN])
        and not normalized[CAPABILITY_ADMIN]
        and await count_active_admins(db, membership["account_id"]) <= 1
    ):
        raise ValueError("Cannot demote the only administrator")

    return True


async def ensure_capabilities_keep_an_admin(
    db,
    membership_id: int,
    capabilities: Mapping[str, Any],
) -> bool:
    """Compatibility wrapper for last-admin demotion checks."""
    return await ensure_membership_can_be_updated(db, membership_id, capabilities)
