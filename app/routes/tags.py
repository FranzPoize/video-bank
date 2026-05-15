"""
Tag routes: listing and filter metadata.

Tags themselves are created on-the-fly during upload/edit (in video_service).
This module provides the tag picker/filter endpoints, plus settings page with tag management.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.services import tag_service
from app.templates import templates, DEFAULT_LANG, get_i18n_context

router = APIRouter()


def _get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback.

    Middleware sets request.state.i18n, but in tests it may not exist.
    """
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))


@router.get("/api/tags")
async def list_tags(db=Depends(get_db)):
    """Return all tags as JSON (for potential autocomplete)."""
    tags = await tag_service.list_all_tags(db)
    return {"tags": [t["name"] for t in tags]}


@router.get("/settings")
async def settings_page(request: Request, db=Depends(get_db)):
    """Settings page with tag management."""
    i18n = _get_i18n(request)
    tags = await tag_service.list_all_tags_with_counts(db)

    # Get error query param for rename errors
    query_params = request.query_params
    error_code = query_params.get("error")

    return templates.TemplateResponse(
        request, "settings.html",
        {
            **i18n,
            "tags": tags,
            "error_code": error_code,
        },
    )


@router.post("/api/tags/{tag_id}/rename")
async def rename_tag(
    request: Request,
    tag_id: int,
    new_name: str = Form(...),
    db=Depends(get_db),
):
    """Rename a tag. Redirects back to settings."""
    try:
        await tag_service.update_tag(db, tag_id, new_name)
        return RedirectResponse(url="/settings", status_code=303)
    except ValueError as e:
        # Pass error via query param for template to display
        msg = str(e).lower()
        if "empty" in msg:
            error_code = "empty"
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
):
    """Delete a tag. Redirects back to settings."""
    await tag_service.delete_tag(db, tag_id)
    return RedirectResponse(url="/settings", status_code=303)
