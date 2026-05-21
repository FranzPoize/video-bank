"""
Authentication services for users and email verification.

Each public function takes an aiosqlite database connection as the first
argument. Passwords and verification tokens are hashed before storage.
"""

from datetime import UTC, datetime, timedelta
from importlib import import_module

import aiosqlite

from app.services import security_service


DUPLICATE_SIGNUP_ERROR = "Unable to create account with these details"
INVALID_LOGIN_ERROR = "Invalid email or password"
UNVERIFIED_LOGIN_ERROR = "Email address is not verified"
INVALID_VERIFICATION_TOKEN_ERROR = "Invalid or expired verification token"
DEFAULT_VERIFICATION_TOKEN_TTL_HOURS = 24


def _utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a datetime for SQLite text comparison and storage."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def get_user_by_id(db: aiosqlite.Connection, user_id: int) -> dict | None:
    """Fetch a user by id. Returns None if the user does not exist."""
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_user_by_email(db: aiosqlite.Connection, email: str) -> dict | None:
    """Fetch a user by normalized email. Returns None if not found."""
    normalized_email = security_service.normalize_email(email)
    cursor = await db.execute(
        "SELECT * FROM users WHERE normalized_email = ?",
        (normalized_email,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_unverified_user(
    db: aiosqlite.Connection,
    email: str,
    password: str,
) -> dict:
    """Create an unverified user. Returns the created user as a dict."""
    display_email = email.strip()
    normalized_email = security_service.normalize_email(email)
    if not display_email or not normalized_email:
        raise ValueError(DUPLICATE_SIGNUP_ERROR)

    password_hash = security_service.hash_password(password)

    try:
        cursor = await db.execute(
            """INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
               VALUES (?, ?, ?, 0)""",
            (display_email, normalized_email, password_hash),
        )
        await db.commit()
    except aiosqlite.IntegrityError as exc:
        await db.rollback()
        if "users.normalized_email" in str(exc) or "UNIQUE" in str(exc):
            raise ValueError(DUPLICATE_SIGNUP_ERROR) from exc
        raise

    user = await get_user_by_id(db, cursor.lastrowid)
    if user is None:
        raise RuntimeError("Created user could not be loaded")
    return user


async def validate_login_credentials(
    db: aiosqlite.Connection,
    email: str,
    password: str,
) -> dict:
    """Validate login credentials and return the verified user."""
    user = await get_user_by_email(db, email)
    if user is None:
        raise ValueError(INVALID_LOGIN_ERROR)

    if not security_service.verify_password(password, user["password_hash"]):
        raise ValueError(INVALID_LOGIN_ERROR)

    if not user["is_email_verified"]:
        raise ValueError(UNVERIFIED_LOGIN_ERROR)

    return user


async def create_email_verification_token(
    db: aiosqlite.Connection,
    user_id: int,
    expires_at: datetime | None = None,
) -> str:
    """Create and store a hashed email verification token. Returns plaintext token."""
    if expires_at is None:
        expires_at = _utcnow() + timedelta(hours=DEFAULT_VERIFICATION_TOKEN_TTL_HOURS)

    token = security_service.create_token()
    token_hash = security_service.hash_token(token)
    await db.execute(
        """INSERT INTO email_verification_tokens (token_hash, user_id, expires_at)
           VALUES (?, ?, ?)""",
        (token_hash, user_id, _serialize_datetime(expires_at)),
    )
    await db.commit()
    return token


async def verify_email_token(
    db: aiosqlite.Connection,
    token: str,
    *,
    create_account: bool = False,
    account_display_name: str | None = None,
    invitation_token: str | None = None,
) -> dict:
    """Verify an email token once and optionally create/activate signup context."""
    token_hash = security_service.hash_token(token)
    cursor = await db.execute(
        """SELECT evt.*, u.email AS user_email
           FROM email_verification_tokens evt
           JOIN users u ON u.id = evt.user_id
           WHERE evt.token_hash = ?
             AND evt.used_at IS NULL
             AND evt.expires_at > ?""",
        (token_hash, _serialize_datetime(_utcnow())),
    )
    token_row = await cursor.fetchone()
    if token_row is None:
        raise ValueError(INVALID_VERIFICATION_TOKEN_ERROR)

    try:
        now_text = _serialize_datetime(_utcnow())
        await db.execute(
            """UPDATE users
               SET is_email_verified = 1,
                   email_verified_at = COALESCE(email_verified_at, ?),
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (now_text, token_row["user_id"]),
        )
        await db.execute(
            "UPDATE email_verification_tokens SET used_at = ? WHERE id = ?",
            (now_text, token_row["id"]),
        )

        if invitation_token:
            await _accept_signup_invitation(db, token_row["user_id"], invitation_token)
        elif create_account:
            await _create_signup_account(
                db,
                token_row["user_id"],
                account_display_name or _default_account_display_name(token_row["user_email"]),
            )

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    user = await get_user_by_id(db, token_row["user_id"])
    if user is None:
        raise RuntimeError("Verified user could not be loaded")
    return user


async def _accept_signup_invitation(
    db: aiosqlite.Connection,
    user_id: int,
    invitation_token: str,
) -> None:
    """Activate a pending invitation after a signup email is verified."""
    invitation_service = import_module("app.services.invitation_service")
    await invitation_service.accept_invitation(db, invitation_token, user_id)


def _default_account_display_name(email: str) -> str:
    """Return a simple default account display name for direct signup."""
    local_part = email.split("@", 1)[0].strip()
    return local_part or "Account"


async def _create_signup_account(
    db: aiosqlite.Connection,
    user_id: int,
    display_name: str,
) -> int:
    """Create an account and admin membership for a verified signup."""
    account_id = await _create_signup_account_with_account_service(db, user_id, display_name)
    if account_id is not None:
        return account_id

    cursor = await db.execute(
        "INSERT INTO accounts (display_name) VALUES (?)",
        (display_name,),
    )
    account_id = cursor.lastrowid
    await db.execute(
        """INSERT INTO account_memberships (
               user_id, account_id, manage_videos, manage_matches, manage_tags,
               manage_account_settings, manage_members, admin, is_active
           ) VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1)""",
        (user_id, account_id),
    )
    return account_id


async def _create_signup_account_with_account_service(
    db: aiosqlite.Connection,
    user_id: int,
    display_name: str,
) -> int | None:
    """Delegate to account_service when a compatible helper exists."""
    try:
        account_service = import_module("app.services.account_service")
    except ModuleNotFoundError:
        return None

    if hasattr(account_service, "create_account_for_verified_signup"):
        result = await account_service.create_account_for_verified_signup(
            db,
            user_id,
            display_name,
        )
        if isinstance(result, dict) and "account" in result:
            return result["account"]["id"]
        if isinstance(result, dict) and "id" in result:
            return result["id"]
        return result

    if hasattr(account_service, "create_account_with_admin_membership"):
        account = await account_service.create_account_with_admin_membership(
            db,
            user_id,
            display_name,
        )
        if isinstance(account, dict) and "account" in account:
            return account["account"]["id"]
        if isinstance(account, dict) and "id" in account:
            return account["id"]
        return account

    if hasattr(account_service, "create_account") and hasattr(account_service, "create_admin_membership"):
        account = await account_service.create_account(db, display_name)
        account_id = account["id"] if isinstance(account, dict) else account
        await account_service.create_admin_membership(db, user_id, account_id)
        return account_id

    return None
