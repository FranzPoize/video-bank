"""
File system operations: save uploads, delete files, generate thumbnails.

Thumbnail generation (ffmpeg) is a placeholder here — actual ffmpeg
call is added in Checkpoint 2.
"""

import asyncio
import os
import shutil
import uuid
from pathlib import Path

# Directories relative to project root
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
VIDEOS_DIR = UPLOAD_DIR / "videos"
THUMBNAILS_DIR = UPLOAD_DIR / "thumbnails"

ALLOWED_EXTENSIONS = {
    e.strip() for e in os.environ.get("ALLOWED_EXTENSIONS", "mp4,webm,mov").split(",")
}
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(500 * 1024 * 1024)))  # 500MB
THUMBNAIL_TIME_SECONDS = int(os.environ.get("THUMBNAIL_TIME", "1"))


def _ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def _get_ext(filename: str) -> str:
    """Extract lowercase extension without dot, e.g. 'mp4'."""
    return Path(filename).suffix.lstrip(".").lower()


def validate_file(filename: str, file_size: int) -> str | None:
    """Return an error message if the file is invalid, or None."""
    ext = _get_ext(filename)
    if not ext:
        return "File has no extension."
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return f"Unsupported format '.{ext}'. Allowed: {allowed}"
    if file_size > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE / (1024 * 1024)
        return f"File too large (max {max_mb:.0f}MB)."
    return None


async def save_upload(file_content: bytes, original_name: str) -> str:
    """Save uploaded bytes to disk. Returns the stored filename (UUID-based)."""
    _ensure_dirs()
    ext = _get_ext(original_name)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = VIDEOS_DIR / stored_name
    with open(dest, "wb") as f:
        f.write(file_content)
    return stored_name


async def delete_video_file(filename: str):
    """Remove a stored video file from disk. No-op if missing."""
    path = VIDEOS_DIR / filename
    if path.exists():
        path.unlink()


async def delete_thumbnail(filename: str):
    """Remove a stored thumbnail from disk. No-op if missing."""
    thumb = THUMBNAILS_DIR / f"{Path(filename).stem}.jpg"
    if thumb.exists():
        thumb.unlink()


async def generate_thumbnail(video_filename: str) -> bool:
    """Generate a thumbnail at the 1-second mark using ffmpeg.
    
    Returns True if thumbnail was generated, False if ffmpeg is unavailable.
    """
    _ensure_dirs()
    video_path = VIDEOS_DIR / video_filename
    thumb_path = THUMBNAILS_DIR / f"{Path(video_filename).stem}.jpg"

    if thumb_path.exists():
        return True  # Already generated

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False

    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-ss", str(THUMBNAIL_TIME_SECONDS),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(thumb_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return_code = await proc.wait()
    return return_code == 0 and thumb_path.exists()


def get_video_path(filename: str) -> Path:
    """Return full path to a stored video file."""
    return VIDEOS_DIR / filename
