"""
Tag routes: listing and filter metadata.

Tags themselves are created on-the-fly during upload/edit (in video_service).
This module provides the tag picker/filter endpoints, plus settings page with tag management.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.dependencies import require_active_account
from app.services import permission_service, tag_service
from app.templates import templates, DEFAULT_LANG, get_i18n, get_i18n_context

router = APIRouter()


def _account_context(active: dict) -> dict:
    """Return template auth/account context for protected pages."""
    can_manage_tags = bool(active["membership"][permission_service.ADMIN]) or bool(
        active["membership"][permission_service.MANAGE_TAGS]
    )
    return {
        "current_user": active["user"],
        "current_account": active["account"],
        "membership": active["membership"],
        "can_manage_tags": can_manage_tags,
        "can_manage_videos": bool(active["membership"][permission_service.ADMIN])
        or bool(active["membership"][permission_service.MANAGE_VIDEOS]),
    }


async def _require_tag_manager(db, active: dict) -> None:
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_TAGS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")


@router.get("/api/tags")
async def list_tags(db=Depends(get_db), active=Depends(require_active_account)):
    """Return all tags as JSON (for potential autocomplete)."""
    tags = await tag_service.list_all_tags(db, account_id=active["account"]["id"])
    return {"tags": [t["name"] for t in tags]}


@router.get("/settings")
async def settings_page(request: Request, db=Depends(get_db), active=Depends(require_active_account)):
    """Settings page with tag management."""
    i18n = get_i18n(request)
    tags = await tag_service.list_all_tags_with_counts(db, account_id=active["account"]["id"])

    # Get error query param for rename errors
    query_params = request.query_params
    error_code = query_params.get("error")

    return templates.TemplateResponse(
        request, "settings.html",
        {
            **i18n,
            "tags": tags,
            "error_code": error_code,
            **_account_context(active),
        },
    )


@router.post("/api/tags/{tag_id}/rename")
async def rename_tag(
    request: Request,
    tag_id: int,
    new_name: str = Form(...),
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Rename a tag. Redirects back to settings."""
    await _require_tag_manager(db, active)
    try:
        await tag_service.update_tag(db, tag_id, new_name, account_id=active["account"]["id"])
        return RedirectResponse(url="/settings", status_code=303)
    except ValueError as e:
        # Pass error via query param for template to display
        msg = str(e).lower()
        if "empty" in msg:
            error_code = "empty"
        elif "not found" in msg:
            raise HTTPException(status_code=404, detail="Tag not found")
        else:
            error_code = "duplicate"
        return RedirectResponse(
            url=f"/settings?error={error_code}",
            status_code=303,
        )


@router.post("/api/tags/{tag_id}/delete")
async def delete_tag_route(
    tag_id: int,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Delete a tag. Redirects back to settings."""
    await _require_tag_manager(db, active)
    deleted = await tag_service.delete_tag(db, tag_id, account_id=active["account"]["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return RedirectResponse(url="/settings", status_code=303)
