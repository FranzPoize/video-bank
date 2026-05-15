"""
Tag routes: listing and filter metadata.

Tags themselves are created on-the-fly during upload/edit (in video_service).
This module provides the tag picker/filter endpoints.
"""

from fastapi import APIRouter, Depends, Request

from app.database import get_db
from app.services import tag_service
from app.templates import templates

router = APIRouter()


@router.get("/api/tags")
async def list_tags(db=Depends(get_db)):
    """Return all tags as JSON (for potential autocomplete)."""
    tags = await tag_service.list_all_tags(db)
    return {"tags": [t["name"] for t in tags]}
