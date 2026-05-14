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
from app.services import video_service
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
async def list_videos(request: Request, db=Depends(get_db)):
    """Show all videos. HTMX requests get just the grid fragment."""
    videos = await video_service.list_videos(db)
    enriched = [_video_to_card(v) for v in videos]

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "_video_grid.html" if is_htmx else "index.html"
    return templates.TemplateResponse(
        request, template, {"videos": enriched}
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
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request, "upload.html",
            {"error": str(e)},
            status_code=400,
        )

    return RedirectResponse(url="/", status_code=303)
