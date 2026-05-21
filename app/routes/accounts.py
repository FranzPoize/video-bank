"""Server-rendered account switching, settings, and member list routes."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.dependencies import require_active_account, require_current_user
from app.services import account_service, permission_service
from app.templates import get_i18n, templates


router = APIRouter()


def _has_membership_capability(membership: dict, capability: str) -> bool:
    """Return whether a loaded membership grants a capability."""
    return bool(membership[permission_service.ADMIN]) or bool(membership[capability])


def _safe_next(next_url: str | None) -> str:
    """Return an internal redirect target for account switch posts."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/account/settings"


async def _account_context(db, active: dict) -> dict:
    """Return shared template context for account pages."""
    accounts = await account_service.list_accounts_for_user(db, active["user"]["id"])
    membership = active["membership"]
    return {
        "current_user": active["user"],
        "current_account": active["account"],
        "current_user_accounts": accounts,
        "membership": membership,
        "can_manage_account_settings": _has_membership_capability(
            membership,
            permission_service.MANAGE_ACCOUNT_SETTINGS,
        ),
        "can_manage_members": _has_membership_capability(
            membership,
            permission_service.MANAGE_MEMBERS,
        ),
    }


@router.get("/accounts")
async def accounts_index(request: Request, db=Depends(get_db), active=Depends(require_active_account)):
    """List switchable accounts, or redirect to settings for single-account users."""
    context = await _account_context(db, active)
    if len(context["current_user_accounts"]) <= 1:
        return RedirectResponse(url="/account/settings", status_code=303)

    return templates.TemplateResponse(
        request,
        "account_settings.html",
        {**get_i18n(request), **context, "members": None, "message": None, "error": None},
    )


@router.post("/accounts/switch")
async def switch_account(
    account_id: int = Form(...),
    next: str = Form("/account/settings"),
    db=Depends(get_db),
    current_user=Depends(require_current_user),
):
    """Switch the current session active account after membership validation."""
    try:
        updated = await account_service.set_session_active_account(
            db,
            current_user["session"]["id"],
            account_id,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Account membership is required")

    if not updated:
        raise HTTPException(status_code=403, detail="Account membership is required")
    return RedirectResponse(url=_safe_next(next), status_code=303)


@router.get("/account/settings")
async def account_settings(request: Request, db=Depends(get_db), active=Depends(require_active_account)):
    """Show account metadata and member summary for the active account."""
    context = await _account_context(db, active)
    members = await account_service.list_account_members(db, active["account"]["id"])
    return templates.TemplateResponse(
        request,
        "account_settings.html",
        {**get_i18n(request), **context, "members": members, "message": None, "error": None},
    )


@router.post("/account/settings")
async def update_account_settings(
    request: Request,
    display_name: str = Form(...),
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Update active account metadata when the user has settings capability."""
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_ACCOUNT_SETTINGS,
        )
        await account_service.update_account_display_name(db, active["account"]["id"], display_name)
    except ValueError as exc:
        if str(exc).startswith("Capability required"):
            raise HTTPException(status_code=403, detail="Capability required")
        context = await _account_context(db, active)
        members = await account_service.list_account_members(db, active["account"]["id"])
        return templates.TemplateResponse(
            request,
            "account_settings.html",
            {**get_i18n(request), **context, "members": members, "message": None, "error": "empty"},
            status_code=400,
        )

    return RedirectResponse(url="/account/settings", status_code=303)


@router.get("/account/members")
async def account_members(request: Request, db=Depends(get_db), active=Depends(require_active_account)):
    """Show active account members and their current capabilities."""
    context = await _account_context(db, active)
    members = await account_service.list_account_members(db, active["account"]["id"])
    return templates.TemplateResponse(
        request,
        "members.html",
        {**get_i18n(request), **context, "members": members},
    )
