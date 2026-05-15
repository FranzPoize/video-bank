"""
File system operations: save uploads, delete files, generate thumbnails.

Thumbnail generation (ffmpeg) is a placeholder here — actual ffmpeg
call is added in Checkpoint 2.
"""

import asyncio
import logging
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
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(2048 * 1024 * 1024)))  # 2GB
THUMBNAIL_TIME_SECONDS = int(os.environ.get("THUMBNAIL_TIME", "1"))
THUMBNAIL_RESOLUTION = "512x288"
THUMBNAIL_EXT = "webp"

logger = logging.getLogger(__name__)


def _ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def get_available_space(directory: Path | None = None) -> dict:
    """Return disk usage info for the given directory.

    Defaults to VIDEOS_DIR. Returns total, used, free (bytes),
    percent_used (0.0–1.0), and free_gb (human-readable, 1 decimal).

    On OSError (e.g. permission denied, missing dir), logs a warning
    and returns {"error": True} so callers can degrade gracefully.
    """
    try:
        usage = shutil.disk_usage(directory or VIDEOS_DIR)
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent_used": usage.used / usage.total,
            "free_gb": round(usage.free / (1024**3), 1),
        }
    except OSError as e:
        logger.warning("Failed to get disk usage: %s", e)
        return {"error": True}


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

    # Disk space guard: reject if uploading would push disk past 95% capacity
    space = get_available_space()
    if not space.get("error"):
        projected = (space["used"] + file_size) / space["total"]
        if projected > 0.95:
            return "Not enough disk space (would exceed 95% capacity)."
        if projected > 0.80:
            logger.warning(
                "Disk near capacity: %.1f%% used (projected: %.1f%%)",
                space["percent_used"] * 100,
                projected * 100,
            )

    return None


async def save_upload(file_content: bytes, original_name: str) -> str:
    """Save uploaded bytes to disk. Returns the stored filename (UUID-based)."""
    _ensure_dirs()
    ext = _get_ext(original_name)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = VIDEOS_DIR / stored_name
    with open(dest, "wb") as f:
        f.write(file_content)
    logger.info("File saved: %s (%d bytes)", stored_name, len(file_content))
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
    thumb_path = THUMBNAILS_DIR / f"{Path(video_filename).stem}.{THUMBNAIL_EXT}"

    if thumb_path.exists():
        return True  # Already generated

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False

    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-ss",
        str(THUMBNAIL_TIME_SECONDS),
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-q:v",
        "85",
        "-sws_flags",
        "lanczos",
        "-s",
        THUMBNAIL_RESOLUTION,
        str(thumb_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return_code = await proc.wait()
    if return_code == 0 and thumb_path.exists():
        logger.info("Thumbnail generated: %s", thumb_path.name)
        return True
    else:
        logger.error(
            "Thumbnail generation failed for %s (ffmpeg returned %d)",
            video_filename,
            return_code,
        )
        return False


def get_video_path(filename: str) -> Path:
    """Return full path to a stored video file."""
    return VIDEOS_DIR / filename
