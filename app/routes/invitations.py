"""Server-rendered invitation creation, revocation, and acceptance routes."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.dependencies import get_current_user_optional, require_active_account
from app.services import account_service, email_service, invitation_service, permission_service
from app.templates import get_i18n, templates


logger = logging.getLogger(__name__)
router = APIRouter()


def _has_membership_capability(membership: dict, capability: str) -> bool:
    """Return whether a loaded membership grants a capability."""
    return bool(membership[permission_service.ADMIN]) or bool(membership[capability])


def _selected_capabilities(capabilities: list[str] | None) -> dict[str, bool]:
    """Normalize submitted checkbox capability values."""
    submitted = set(capabilities or [])
    return permission_service.normalize_capabilities(
        {capability: capability in submitted for capability in permission_service.ALL_CAPABILITIES}
    )


def _selected_capabilities_from_form(capabilities: list[str] | None, form: dict) -> dict[str, bool]:
    """Normalize list-style and legacy checkbox-style capability form fields."""
    selected = set(capabilities or [])
    for capability in permission_service.ALL_CAPABILITIES:
        if form.get(capability):
            selected.add(capability)
    return _selected_capabilities(list(selected))


async def _account_context(db, active: dict) -> dict:
    """Return shared account template context."""
    accounts = await account_service.list_accounts_for_user(db, active["user"]["id"])
    membership = active["membership"]
    return {
        "current_user": active["user"],
        "current_account": active["account"],
        "current_user_accounts": accounts,
        "membership": membership,
        "can_manage_members": _has_membership_capability(membership, permission_service.MANAGE_MEMBERS),
        "can_manage_videos": _has_membership_capability(membership, permission_service.MANAGE_VIDEOS),
    }


async def _list_pending_invitations(db, account_id: int) -> list[dict]:
    """Return pending invitations for account invitation management UI."""
    cursor = await db.execute(
        """
        SELECT id, invited_email, expires_at, manage_videos, manage_matches, manage_tags,
               manage_account_settings, manage_members, admin
        FROM invitations
        WHERE account_id = ? AND accepted_at IS NULL AND revoked_at IS NULL
        ORDER BY created_at DESC, id DESC
        """,
        (account_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _invitation_url(request: Request, token: str) -> str:
    """Build an absolute invitation acceptance URL for outgoing emails."""
    return str(request.url_for("accept_invitation_form")) + f"?token={token}"


def _signup_invitation_url(token: str) -> str:
    """Build a safe signup URL preserving invitation context."""
    return f"/signup?invitation_token={quote(token, safe='')}"


def _accept_invitation_url(token: str) -> str:
    """Build a safe invitation acceptance GET URL."""
    return f"/invitations/accept?token={quote(token, safe='')}"


def _public_context(current_session: dict | None = None) -> dict:
    """Return auth context for public invitation pages."""
    return {
        "current_user": current_session["user"] if current_session else None,
        "current_account": None,
    }


@router.get("/account/invitations/new")
async def new_invitation_form(request: Request, db=Depends(get_db), active=Depends(require_active_account)):
    """Render the account invitation form."""
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_MEMBERS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")

    context = await _account_context(db, active)
    pending_invitations = await _list_pending_invitations(db, active["account"]["id"])
    return templates.TemplateResponse(
        request,
        "invite_form.html",
        {
            **get_i18n(request),
            **context,
            "email": "",
            "selected_capabilities": {},
            "sent": request.query_params.get("sent") == "1",
            "revoked": request.query_params.get("revoked") == "1",
            "error": None,
            "capabilities": permission_service.ALL_CAPABILITIES,
            "pending_invitations": pending_invitations,
        },
    )


@router.post("/account/invitations")
async def create_invitation(
    request: Request,
    email: str = Form(""),
    invited_email: str = Form(""),
    capabilities: list[str] = Form([]),
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Create an account invitation and send the acceptance email."""
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_MEMBERS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")

    form = await request.form()
    selected = _selected_capabilities_from_form(capabilities, form)
    target_email = invited_email or email
    try:
        invitation = await invitation_service.create_invitation(
            db,
            account_id=active["account"]["id"],
            invited_email=target_email,
            inviter_user_id=active["user"]["id"],
            capabilities=selected,
        )
    except ValueError:
        context = await _account_context(db, active)
        pending_invitations = await _list_pending_invitations(db, active["account"]["id"])
        return templates.TemplateResponse(
            request,
            "invite_form.html",
            {
                **get_i18n(request),
                **context,
                "email": target_email,
                "selected_capabilities": selected,
                "sent": False,
                "revoked": False,
                "error": "invalid",
                "capabilities": permission_service.ALL_CAPABILITIES,
                "pending_invitations": pending_invitations,
            },
            status_code=400,
        )

    try:
        email_service.send_invitation_email(
            invitation["invited_email"],
            inviter_email=active["user"]["email"],
            account_name=active["account"]["display_name"],
            invitation_url=_invitation_url(request, invitation["token"]),
        )
    except RuntimeError:
        logger.exception("Failed to send invitation email for invitation_id=%s", invitation["id"])
        context = await _account_context(db, active)
        pending_invitations = await _list_pending_invitations(db, active["account"]["id"])
        return templates.TemplateResponse(
            request,
            "invite_form.html",
            {
                **get_i18n(request),
                **context,
                "email": "",
                "selected_capabilities": {},
                "sent": False,
                "revoked": False,
                "error": "email_failed",
                "capabilities": permission_service.ALL_CAPABILITIES,
                "pending_invitations": pending_invitations,
            },
            status_code=500,
        )

    return RedirectResponse(url="/account/invitations/new?sent=1", status_code=303)


@router.post("/account/invitations/{invitation_id}/revoke")
async def revoke_invitation(invitation_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Revoke a pending account invitation."""
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_MEMBERS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")

    try:
        revoked = await invitation_service.revoke_invitation(
            db,
            invitation_id,
            active["account"]["id"],
            active["user"]["id"],
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return RedirectResponse(url="/account/invitations/new?revoked=1", status_code=303)


@router.get("/invitations/accept", name="accept_invitation_form")
async def accept_invitation_form(
    request: Request,
    token: str = "",
    db=Depends(get_db),
    current_session=Depends(get_current_user_optional),
):
    """Render the invitation acceptance flow."""
    invitation = await invitation_service.get_invitation_by_token(db, token)
    status = "ready" if invitation and invitation_service.invitation_is_pending(invitation) else "invalid"
    return templates.TemplateResponse(
        request,
        "invitation_accept.html",
        {**get_i18n(request), **_public_context(current_session), "invitation": invitation, "token": token, "status": status},
    )


@router.post("/invitations/accept")
async def accept_invitation(
    request: Request,
    token: str = Form(...),
    db=Depends(get_db),
    current_session=Depends(get_current_user_optional),
):
    """Accept an invitation and redirect after POST for every navigation outcome."""
    invitation = await invitation_service.get_invitation_by_token(db, token)
    if invitation is None or not invitation_service.invitation_is_pending(invitation):
        return RedirectResponse(url=_accept_invitation_url(token), status_code=303)

    if current_session is None or not current_session["user"].get("is_email_verified"):
        return RedirectResponse(url=_signup_invitation_url(token), status_code=303)

    try:
        await invitation_service.accept_invitation(db, token, current_session["user"]["id"])
    except ValueError:
        return RedirectResponse(url=_accept_invitation_url(token), status_code=303)

    return RedirectResponse(url="/account/settings?invitation_accepted=1", status_code=303)
