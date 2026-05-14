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
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services import tag_service, video_service
from app.services.file_service import get_video_path

router = APIRouter()
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


def _video_to_card(video: dict) -> dict:
    """Enrich a video dict with template-friendly fields."""
    thumb_stem = Path(video["filename"]).stem
    thumb_path = (
        Path(__file__).resolve().parent.parent.parent
        / "uploads"
        / "thumbnails"
        / f"{thumb_stem}.jpg"
    )
    has_thumbnail = thumb_path.exists()
    return {
        **video,
        "has_thumbnail": has_thumbnail,
        "thumbnail_url": f"/uploads/thumbnails/{thumb_stem}.jpg" if has_thumbnail else None,
    }


@router.get("/")
async def list_videos(
    request: Request,
    tag_id: int | None = None,
    db=Depends(get_db),
):
    """Show all videos, optionally filtered by tag_id. HTMX requests get just the grid fragment."""
    if tag_id is not None:
        videos = await video_service.list_videos_by_tag(db, tag_id)
    else:
        videos = await video_service.list_videos_with_tags(db)

    enriched = [_video_to_card(v) for v in videos]
    all_tags = await tag_service.list_all_tags(db)

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "_content.html" if is_htmx else "index.html"

    return templates.TemplateResponse(
        request, template,
        {
            "videos": enriched,
            "all_tags": all_tags,
            "active_tag_id": tag_id,
        },
    )


@router.get("/upload")
async def upload_form(request: Request):
    """Show the upload form."""
    return templates.TemplateResponse(request, "upload.html")


@router.post("/api/videos")
async def create_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form(""),  # Comma-separated tags
    db=Depends(get_db),
):
    """Handle video upload. Redirects to list on success."""
    # Read file content
    content = await file.read()

    try:
        await video_service.create_video(
            db,
            name=name,
            file_content=content,
            original_name=file.filename or "untitled",
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
            tags=tags,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request, "upload.html",
            {"error": str(e)},
            status_code=400,
        )

    return RedirectResponse(url="/", status_code=303)


@router.get("/api/video/{video_id}/file")
async def stream_video(video_id: int, db=Depends(get_db)):
    """Stream a video file with range request support for seeking."""
    video = await video_service.get_video(db, video_id)
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


@router.get("/video/{video_id}")
async def video_detail(request: Request, video_id: int, db=Depends(get_db)):
    """Show video detail page with player and tags."""
    video = await video_service.get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    enriched = _video_to_card(video)
    thumb_stem = Path(video["filename"]).stem
    enriched["video_url"] = f"/api/video/{video_id}/file"
    enriched["thumbnail_url"] = f"/uploads/thumbnails/{thumb_stem}.jpg"
    enriched["has_thumbnail"] = (
        Path(__file__).resolve().parent.parent.parent
        / "uploads"
        / "thumbnails"
        / f"{thumb_stem}.jpg"
    ).exists()

    return templates.TemplateResponse(
        request, "video_detail.html",
        {"video": enriched},
    )


@router.get("/video/{video_id}/edit")
async def edit_video_form(request: Request, video_id: int, db=Depends(get_db)):
    """Show the edit form for a video."""
    video = await video_service.get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    return templates.TemplateResponse(
        request, "edit.html",
        {
            "video": video,
            "tags_str": ", ".join(video.get("tags", [])),
        },
    )


@router.post("/video/{video_id}/edit")
async def update_video(
    request: Request,
    video_id: int,
    name: str = Form(...),
    tags: str = Form(""),
    db=Depends(get_db),
):
    """Update a video's name and tags."""
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    await video_service.update_video(db, video_id, name)

    # Update tags
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    await tag_service.set_video_tags(db, video_id, tag_names)

    return RedirectResponse(url=f"/video/{video_id}", status_code=303)


@router.post("/video/{video_id}/delete")
async def delete_video(video_id: int, db=Depends(get_db)):
    """Delete a video and its files."""
    deleted = await video_service.delete_video(db, video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return RedirectResponse(url="/", status_code=303)
