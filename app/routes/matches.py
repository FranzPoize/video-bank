"""
Match routes: list, create, detail, edit, delete, video linking.

Registers the home page (GET /) which now shows match list.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.services import match_service
from app.services.stats_calculator import compute_all
from app.templates import templates, get_i18n

router = APIRouter()

# Allowed stat field names for form parsing
_STAT_FIELDS = [
    "minutes_played", "points",
    "two_point_attempts", "two_point_made",
    "three_point_attempts", "three_point_made",
    "free_throw_attempts", "free_throw_made",
    "offensive_rebounds", "defensive_rebounds", "total_rebounds",
    "assists", "steals", "blocks", "turnovers", "personal_fouls",
]


def _parse_stat(value: str | None) -> int | float | None:
    """Parse a form field to int/float or None if empty/invalid."""
    if not value or not value.strip():
        return None
    try:
        # minutes_played is a REAL (float), everything else is INTEGER
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_match_form(form_data: dict) -> dict:
    """Extract match fields from form data, parsing stats as numbers."""
    fields = {
        "name": form_data.get("name", "").strip(),
        "match_date": form_data.get("match_date", "").strip(),
        "opponent": form_data.get("opponent", "").strip(),
        "location": form_data.get("location", "").strip(),
        "notes": form_data.get("notes", "").strip(),
    }
    for field in _STAT_FIELDS:
        fields[field] = _parse_stat(form_data.get(field))
    return fields


@router.get("/")
async def list_matches(request: Request, db=Depends(get_db)):
    """Home page — show all matches ordered by date descending."""
    i18n = get_i18n(request)
    matches = await match_service.list_matches(db)
    return templates.TemplateResponse(
        request,
        "match_list.html",
        {**i18n, "matches": matches},
    )


@router.get("/matches/new")
async def new_match_form(request: Request):
    """Show the create match form."""
    i18n = get_i18n(request)
    return templates.TemplateResponse(
        request,
        "match_form.html",
        {**i18n, "match": None},
    )


@router.post("/api/matches")
async def create_match(request: Request, db=Depends(get_db)):
    """Create a new match from form data."""
    i18n = get_i18n(request)
    form = await request.form()
    fields = _parse_match_form(dict(form))

    # Validate required fields
    errors = []
    if not fields["name"]:
        errors.append("Match name is required")
    if not fields["match_date"]:
        errors.append("Match date is required")

    if errors:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": fields, "errors": errors},
            status_code=400,
        )

    # Separate stat fields from metadata
    name = fields.pop("name")
    match_date = fields.pop("match_date")
    opponent = fields.pop("opponent")
    location = fields.pop("location")
    notes = fields.pop("notes")
    stats = {k: fields[k] for k in _STAT_FIELDS}

    try:
        match = await match_service.create_match(
            db, name=name, match_date=match_date,
            opponent=opponent, location=location, notes=notes,
            **stats,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": {**fields, "name": name, "match_date": match_date}, "errors": [str(e)]},
            status_code=400,
        )

    return RedirectResponse(url=f"/matches/{match['id']}", status_code=303)


@router.get("/matches/{match_id}")
async def match_detail(request: Request, match_id: int, db=Depends(get_db)):
    """Match detail page with stats and linked videos."""
    i18n = get_i18n(request)
    result = await match_service.get_match_with_videos(db, match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Match not found")

    computed = compute_all(result)
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "match_detail.html",
        {**i18n, "match": result, "computed": computed, "unlinked_videos": unlinked, "refresh_player": False},
    )


@router.get("/api/matches/{match_id}/videos/{video_id}/player")
async def match_video_player(
    request: Request,
    match_id: int,
    video_id: int,
    db=Depends(get_db),
):
    """HTMX fragment: return video player HTML for a given match video."""
    i18n = get_i18n(request)
    from app.services.video_service import get_video_with_tags

    video = await get_video_with_tags(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    return templates.TemplateResponse(
        request,
        "_match_video_player.html",
        {**i18n, "video": video},
    )


@router.get("/matches/{match_id}/edit")
async def edit_match_form(request: Request, match_id: int, db=Depends(get_db)):
    """Show the edit match form."""
    i18n = get_i18n(request)
    match = await match_service.get_match(db, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    return templates.TemplateResponse(
        request,
        "match_form.html",
        {**i18n, "match": match},
    )


@router.post("/api/matches/{match_id}")
async def update_match(request: Request, match_id: int, db=Depends(get_db)):
    """Update an existing match."""
    i18n = get_i18n(request)

    # Verify match exists
    existing = await match_service.get_match(db, match_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Match not found")

    form = await request.form()
    fields = _parse_match_form(dict(form))

    if not fields["name"]:
        return templates.TemplateResponse(
            request,
            "match_form.html",
            {**i18n, "match": {**existing, **fields}, "errors": ["Match name is required"]},
            status_code=400,
        )

    await match_service.update_match(db, match_id, **fields)
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/delete")
async def delete_match(match_id: int, db=Depends(get_db)):
    """Delete a match and its associations."""
    deleted = await match_service.delete_match(db, match_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Match not found")
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/matches/{match_id}/videos")
async def link_video(
    request: Request,
    match_id: int,
    video_id: int = Form(...),
    db=Depends(get_db),
):
    """Link a video to a match. Returns HTMX fragment."""
    i18n = get_i18n(request)

    # Verify match exists
    match = await match_service.get_match(db, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    await match_service.link_video(db, match_id, video_id)

    # Refresh data for HTMX fragment re-render
    result = await match_service.get_match_with_videos(db, match_id)
    computed = compute_all(result or {})
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "_match_videos.html",
        {
            **i18n,
            "match": {"id": match_id, "videos": result.get("videos", []) if result else []},
            "computed": computed,
            "unlinked_videos": unlinked,
            "refresh_player": False,
        },
    )


@router.post("/api/matches/{match_id}/videos/{video_id}/remove")
async def unlink_video(
    request: Request,
    match_id: int,
    video_id: int,
    db=Depends(get_db),
):
    """Remove a video from a match. Returns HTMX fragment."""
    i18n = get_i18n(request)
    await match_service.unlink_video(db, match_id, video_id)

    # Refresh data for HTMX fragment re-render
    result = await match_service.get_match_with_videos(db, match_id)
    unlinked = await match_service.get_unlinked_videos(db, match_id)

    return templates.TemplateResponse(
        request,
        "_match_videos.html",
        {
            **i18n,
            "match": {"id": match_id, "videos": result.get("videos", []) if result else []},
            "unlinked_videos": unlinked,
            "refresh_player": True,
        },
    )
