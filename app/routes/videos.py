"""
Video routes: upload, list, detail, stream, edit, delete.

In Checkpoint 1: upload + list only.
Endpoints added incrementally per checkpoint:
  CP2: GET /video/{id} (detail), GET /api/video/{id}/file (stream)
  CP3: Tag handling on upload
  CP5: POST /video/{id}/edit, POST /video/{id}/delete
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.database import get_db
from app.dependencies import require_active_account
from app.services import clip_service, tag_service, video_service
from app.services import permission_service
from app.services.file_service import THUMBNAILS_DIR, THUMBNAIL_EXT, get_available_space, get_video_path
from app.templates import (
    DEFAULT_LANG,
    LANG_FLAGS,
    get_i18n,
    get_i18n_context,
    templates,
)

router = APIRouter()

# Supported languages (from LANG_FLAGS keys)
SUPPORTED_LANGS = set(LANG_FLAGS.keys())


def _video_to_card(video: dict) -> dict:
    """Enrich a video dict with template-friendly fields."""
    thumb_stem = Path(video["filename"]).stem
    thumb_path = (
        Path(__file__).resolve().parent.parent.parent
        / "uploads"
        / "thumbnails"
        / f"{thumb_stem}.{THUMBNAIL_EXT}"
    )
    has_thumbnail = thumb_path.exists()
    return {
        **video,
        "has_thumbnail": has_thumbnail,
        "thumbnail_url": f"/api/videos/{video['id']}/thumbnail"
        if has_thumbnail
        else None,
    }


def _account_context(active: dict) -> dict:
    """Return template auth/account context for protected pages."""
    return {
        "current_user": active["user"],
        "current_account": active["account"],
        "membership": active["membership"],
        "can_manage_videos": bool(active["membership"][permission_service.ADMIN])
        or bool(active["membership"][permission_service.MANAGE_VIDEOS]),
    }


async def _require_video_manager(db, active: dict) -> None:
    try:
        await permission_service.require_capability(
            db,
            active["user"]["id"],
            active["account"]["id"],
            permission_service.MANAGE_VIDEOS,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability required")


@router.get("/api/space")
async def space_indicator(request: Request, active=Depends(require_active_account)):
    """Return an HTML fragment showing available disk space in the uploads directory.

    This is consumed by the nav bar's hx-get in base.html. Never blocks
    an upload — returns a gray "Space: unknown" on error.
    """
    i18n = get_i18n(request)
    space = get_available_space()
    return templates.TemplateResponse(
        request,
        "_space_fragment.html",
        {
            **i18n,
            "space": space,
        },
    )


@router.get("/api/videos/{video_id}/thumbnail")
async def video_thumbnail(video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Return a video's thumbnail for the active account only."""
    video = await video_service.get_video(db, video_id, account_id=active["account"]["id"])
    if video is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumb_stem = Path(video["filename"]).stem
    thumb_path = THUMBNAILS_DIR / f"{thumb_stem}.{THUMBNAIL_EXT}"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(path=str(thumb_path), media_type=f"image/{THUMBNAIL_EXT}")


@router.post("/api/lang")
async def switch_language(request: Request):
    """Switch the user's language via cookie.

    Accepts JSON body: {"lang": "fr"} or form data.
    Sets a 30-day cookie and returns HX-Redirect header for HTMX.
    """
    # Try to get lang from JSON body first
    try:
        body = await request.json()
        lang = body.get("lang")
    except Exception:
        # Fall back to form data
        form = await request.form()
        lang = form.get("lang") if form else None

    # Validate language - only allow supported languages
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    # Get redirect target (referer or homepage)
    referer = request.headers.get("referer", "/")

    # For HTMX requests, return HX-Redirect header
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx:
        response = JSONResponse({"success": True})
        response.headers["HX-Redirect"] = referer
    else:
        response = RedirectResponse(url=referer, status_code=303)

    # Set language cookie (30 days = 2592000 seconds)
    response.set_cookie(
        key="lang",
        value=lang,
        max_age=2592000,
        path="/",
        samesite="lax",
    )

    return response


@router.get("/videos")
async def list_videos(
    request: Request,
    tag_id: int | None = None,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Show all videos, optionally filtered by tag_id. HTMX requests get just the grid fragment."""
    i18n = get_i18n(request)
    account_id = active["account"]["id"]
    if tag_id is not None:
        videos = await video_service.list_videos_by_tag(db, tag_id, account_id=account_id)
    else:
        videos = await video_service.list_videos_with_tags(db, account_id=account_id)

    enriched = [_video_to_card(v) for v in videos]
    all_tags = await tag_service.list_all_tags(db, account_id=account_id)

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "_content.html" if is_htmx else "index.html"

    return templates.TemplateResponse(
        request,
        template,
        {
            **i18n,
            "videos": enriched,
            "all_tags": all_tags,
            "active_tag_id": tag_id,
            **_account_context(active),
        },
    )


@router.get("/upload")
async def upload_form(request: Request, active=Depends(require_active_account)):
    """Show the upload form."""
    i18n = get_i18n(request)
    return templates.TemplateResponse(
        request,
        "upload.html",
        {**i18n, **_account_context(active)},
    )


@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form(""),  # Comma-separated tags
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Handle video upload. Redirects to list on success.

    When `X-Requested-With: XMLHttpRequest` is present, returns JSON
    instead of a redirect (for XHR uploads via upload.js).
    """
    i18n = get_i18n(request)
    await _require_video_manager(db, active)
    account_id = active["account"]["id"]
    # Read file content
    content = await file.read()

    try:
        video = await video_service.create_video(
            db,
            name=name,
            file_content=content,
            original_name=file.filename or "untitled",
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
            account_id=account_id,
            tags=tags,
        )
    except ValueError as e:
        # XHR requests get JSON errors too
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"error": str(e)}, status_code=400)
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                **i18n,
                **_account_context(active),
                "error": str(e),
            },
            status_code=400,
        )

    # Return JSON for XHR uploads so JS can handle the response
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"id": video["id"], "redirect": "/videos"})

    return RedirectResponse(url="/videos", status_code=303)


@router.get("/api/videos/{video_id}/file")
async def stream_video(video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Stream a video file with range request support for seeking."""
    video = await video_service.get_video(db, video_id, account_id=active["account"]["id"])
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = get_video_path(video["filename"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(video_path),
        media_type=video["mime_type"],
        filename=video["original_name"],
    )


@router.get("/videos/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Show video detail page with player and tags."""
    i18n = get_i18n(request)
    account_id = active["account"]["id"]
    video = await video_service.get_video_with_tags(db, video_id, account_id=account_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    enriched["video_url"] = f"/api/videos/{video_id}/file"

    # Get matches this video belongs to
    from app.services.match_service import get_video_matches
    video_matches = await get_video_matches(db, video_id, account_id=account_id)

    return templates.TemplateResponse(
        request,
        "video_detail.html",
        {
            **i18n,
            "video": enriched,
            "video_matches": video_matches,
            **_account_context(active),
        },
    )


@router.get("/videos/{video_id}/edit")
async def edit_video_form(request: Request, video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Show the edit form for a video."""
    i18n = get_i18n(request)
    video = await video_service.get_video_with_tags(db, video_id, account_id=active["account"]["id"])
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            **i18n,
            "video": video,
            "tags_str": ", ".join(video.get("tags", [])),
            **_account_context(active),
        },
    )


@router.post("/videos/{video_id}/edit")
async def update_video(
    request: Request,
    video_id: int,
    name: str = Form(...),
    tags: str = Form(""),
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Update a video's name and tags."""
    await _require_video_manager(db, active)
    account_id = active["account"]["id"]
    video = await video_service.get_video(db, video_id, account_id=account_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    await video_service.update_video(db, video_id, name, account_id=account_id)

    # Update tags
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    await tag_service.set_video_tags(db, video_id, tag_names, account_id=account_id)

    return RedirectResponse(url=f"/videos/{video_id}", status_code=303)


@router.post("/videos/{video_id}/delete")
async def delete_video(video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Delete a video and its files."""
    await _require_video_manager(db, active)
    deleted = await video_service.delete_video(db, video_id, account_id=active["account"]["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return RedirectResponse(url="/videos", status_code=303)


@router.get("/videos/{video_id}/clip")
async def clip_form(request: Request, video_id: int, db=Depends(get_db), active=Depends(require_active_account)):
    """Show the clip creator interface for a video."""
    i18n = get_i18n(request)
    video = await video_service.get_video_with_tags(db, video_id, account_id=active["account"]["id"])
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    enriched["video_url"] = f"/api/videos/{video_id}/file"

    return templates.TemplateResponse(
        request,
        "clip.html",
        {
            **i18n,
            "video": enriched,
            **_account_context(active),
        },
    )


@router.post("/api/videos/{video_id}/clip")
async def create_clip(
    request: Request,
    video_id: int,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Create a clip from a source video. Accepts JSON body with start/end."""
    await _require_video_manager(db, active)
    account_id = active["account"]["id"]
    # Parse JSON body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    start = body.get("start")
    end = body.get("end")

    if start is None or end is None:
        raise HTTPException(
            status_code=400,
            detail="Both 'start' and 'end' fields are required.",
        )

    try:
        start = float(start)
        end = float(end)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="'start' and 'end' must be numeric values.",
        )

    # Check source video exists (returns 404 instead of 400)
    source = await video_service.get_video(db, video_id, account_id=account_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source video not found")

    try:
        clip = await clip_service.create_clip(db, video_id, start, end, account_id=account_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"id": clip["id"], "redirect": f"/videos/{clip['id']}"})


@router.post("/api/videos/{video_id}/cut")
async def cut_video(
    request: Request,
    video_id: int,
    db=Depends(get_db),
    active=Depends(require_active_account),
):
    """Remove a segment from a video in-place. Accepts JSON body with start/end."""
    await _require_video_manager(db, active)
    account_id = active["account"]["id"]
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    start = body.get("start")
    end = body.get("end")

    if start is None or end is None:
        raise HTTPException(
            status_code=400,
            detail="Both 'start' and 'end' fields are required.",
        )

    try:
        start = float(start)
        end = float(end)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="'start' and 'end' must be numeric values.",
        )

    # Check video exists (404 vs 400)
    video = await video_service.get_video(db, video_id, account_id=account_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        updated = await clip_service.cut_video(db, video_id, start, end, account_id=account_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"id": updated["id"], "redirect": f"/videos/{updated['id']}"})
