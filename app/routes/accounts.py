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
        "can_manage_videos": _has_membership_capability(
            membership,
            permission_service.MANAGE_VIDEOS,
        ),
    }


def _capabilities_from_form(
    manage_videos: bool,
    manage_matches: bool,
    manage_tags: bool,
    manage_account_settings: bool,
    manage_members: bool,
    admin: bool,
) -> dict[str, bool]:
    """Return a complete capability mapping from checkbox form values."""
    return {
        permission_service.MANAGE_VIDEOS: manage_videos,
        permission_service.MANAGE_MATCHES: manage_matches,
        permission_service.MANAGE_TAGS: manage_tags,
        permission_service.MANAGE_ACCOUNT_SETTINGS: manage_account_settings,
        permission_service.MANAGE_MEMBERS: manage_members,
        permission_service.ADMIN: admin,
    }


async def _require_member_manager(db, active: dict):
    """Require manage_members on the active account."""
    try:
        return await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_MEMBERS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")


async def _load_target_member(db, active: dict, membership_id: int) -> dict:
    """Load a member in the active account or raise 404."""
    member = await account_service.get_member_summary_by_membership_id(db, membership_id)
    if member is None or member["account_id"] != active["account"]["id"]:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


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
        {**get_i18n(request), **context, "members": members, "error": None},
    )


@router.get("/account/members/{membership_id}/rights")
async def edit_member_rights(
    membership_id: int,
    request: Request,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Show the rights editor for an active account member."""
    await _require_member_manager(db, active)
    target_member = await _load_target_member(db, active, membership_id)
    context = await _account_context(db, active)
    return templates.TemplateResponse(
        request,
        "member_rights.html",
        {**get_i18n(request), **context, "target_member": target_member, "error": None},
    )


@router.post("/account/members/{membership_id}/rights")
async def update_member_rights(
    membership_id: int,
    request: Request,
    manage_videos: bool = Form(False),
    manage_matches: bool = Form(False),
    manage_tags: bool = Form(False),
    manage_account_settings: bool = Form(False),
    manage_members: bool = Form(False),
    admin: bool = Form(False),
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Save rights for an active account member."""
    await _require_member_manager(db, active)
    target_member = await _load_target_member(db, active, membership_id)
    capabilities = _capabilities_from_form(
        manage_videos,
        manage_matches,
        manage_tags,
        manage_account_settings,
        manage_members,
        admin,
    )
    try:
        updated = await account_service.update_member_capabilities(db, membership_id, capabilities)
    except ValueError as exc:
        context = await _account_context(db, active)
        return templates.TemplateResponse(
            request,
            "member_rights.html",
            {**get_i18n(request), **context, "target_member": target_member, "error": str(exc)},
            status_code=400,
        )

    if updated is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return RedirectResponse(url="/account/members", status_code=303)


@router.post("/account/members/{membership_id}/remove")
async def remove_member(
    membership_id: int,
    request: Request,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Remove an active member while keeping at least one administrator."""
    await _require_member_manager(db, active)
    await _load_target_member(db, active, membership_id)
    try:
        removed = await account_service.remove_member(db, membership_id)
    except ValueError as exc:
        context = await _account_context(db, active)
        members = await account_service.list_account_members(db, active["account"]["id"])
        return templates.TemplateResponse(
            request,
            "members.html",
            {**get_i18n(request), **context, "members": members, "error": str(exc)},
            status_code=400,
        )

    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return RedirectResponse(url="/account/members", status_code=303)
