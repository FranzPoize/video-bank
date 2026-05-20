"""Authentication dependencies and cookie settings for route handlers."""

import os

from fastapi import Depends, HTTPException, Request

from app.database import get_db
from app.services import account_service, auth_service, session_service


SESSION_COOKIE_NAME = "video_bank_session"
AUTH_SESSION_COOKIE = SESSION_COOKIE_NAME
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SAMESITE = "lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


async def get_current_user_optional(request: Request, db=Depends(get_db)) -> dict | None:
    """Return the current session/user context, or None for anonymous requests."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    session = await session_service.load_session(db, token)
    if session is None:
        return None

    user = await auth_service.get_user_by_id(db, session["user_id"])
    if user is None:
        return None

    safe_user = {key: value for key, value in user.items() if key != "password_hash"}
    return {**safe_user, "user": safe_user, "session": session, "token": token}


async def require_current_user(request: Request, db=Depends(get_db)) -> dict:
    """Require a valid current session/user context."""
    current_user = await get_current_user_optional(request, db)
    if current_user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return current_user


async def require_active_account(request: Request, db=Depends(get_db)) -> dict:
    """Require a current user with an active account membership."""
    current_user = await require_current_user(request, db)
    account_id = current_user["session"].get("active_account_id")

    membership = None
    if account_id is not None:
        membership = await account_service.get_membership(db, current_user["user"]["id"], account_id)

    if membership is None:
        accounts = await account_service.list_accounts_for_user(db, current_user["user"]["id"])
        if not accounts:
            raise HTTPException(status_code=403, detail="No active account")
        account_id = accounts[0]["id"]
        membership = await account_service.get_membership(db, current_user["user"]["id"], account_id)
        if membership is None:
            raise HTTPException(status_code=403, detail="No active account")
        await account_service.set_session_active_account(db, current_user["session"]["id"], account_id)
        current_user["session"]["active_account_id"] = account_id

    account = await account_service.get_account(db, account_id)
    if account is None:
        raise HTTPException(status_code=403, detail="No active account")

    return {**current_user, "account": account, "membership": membership}
