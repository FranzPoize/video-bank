"""
Clip creation service: extract clips from existing videos using ffmpeg.

Relies on ffmpeg/ffprobe being available on the system PATH
(checked at app startup in main.py).
"""

import asyncio
import logging
import math
import shutil
import uuid
from pathlib import Path

import aiosqlite

from app.services import file_service, tag_service, video_service

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────


async def _get_video_duration(video_path: Path) -> float | None:
    """Return video duration in seconds via ffprobe, or None if unavailable."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None

    proc = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None

    try:
        return float(stdout.decode().strip())
    except (ValueError, TypeError):
        return None


def _validate_times(start: float, end: float, duration: float | None):
    """Validate clip time bounds. Raises ValueError with a user-facing message."""
    if start < 0:
        raise ValueError("Start time must be non-negative.")
    if end <= start:
        raise ValueError("Start must be before end.")
    if (end - start) < 1.0:
        raise ValueError("Minimum clip duration is 1 second.")
    if duration is not None and end > duration:
        raise ValueError(
            f"End time ({end:.1f}s) exceeds video duration ({duration:.1f}s)."
        )


def _generate_clip_filename(source_filename: str, start: float, end: float) -> str:
    """Generate a unique filename for the clip, e.g. clip_abc123_10_30.mp4."""
    ext = Path(source_filename).suffix
    stem = Path(source_filename).stem
    # Use a short UUID to avoid filename length issues
    short_id = uuid.uuid4().hex[:8]
    # Round times to 1 decimal for readable filenames
    start_str = f"{start:.1f}".replace(".", "_")
    end_str = f"{end:.1f}".replace(".", "_")
    return f"clip_{stem}_{start_str}_{end_str}_{short_id}{ext}"


# ── Helper: run ffmpeg subprocess ────────────────────────────────


async def _run_ffmpeg(args: list[str]) -> bytes:
    """Run ffmpeg with the given args.  Raises RuntimeError on failure.

    The ``-y`` flag is prepended automatically.  *args* must **not**
    contain the ffmpeg binary path (it is resolved via ``shutil.which``).
    Returns stderr output for diagnostics.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found. Install with: sudo apt install ffmpeg")

    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg failed: {error_msg}")

    return stderr


async def _has_audio_stream(video_path: Path) -> bool:
    """Return True if the video has at least one audio stream."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return False
    proc = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode == 0 and stdout.decode().strip() == "audio"


# ── Cut (in-place trim) ──────────────────────────────────────────


async def cut_video(
    db: aiosqlite.Connection,
    video_id: int,
    start_time: float,
    end_time: float,
) -> dict:
    """Remove the segment [start_time, end_time] from a video in-place.

    Uses one of three strategies depending on which edges are being cut:

    * **Trim from end only** (start == 0): re-encode via **trim** filter.
    * **Trim from start only** (end == duration): re-encode via **trim**
      filter.
    * **Cut a middle segment** (both edges): re-encode via the **trim+concat**
      filter, which splits the video into two sections, drops the removed
      range, and stitches the remainders together.

    All paths use per-frame (re-encode) trimming so they are not
    limited to keyframe alignment.

    The DB record is updated with the new file size, and the thumbnail is
    regenerated.
    """
    # 1. Fetch video
    video = await video_service.get_video(db, video_id)
    if video is None:
        raise ValueError(f"Video with id {video_id} not found.")

    video_path = file_service.get_video_path(video["filename"])
    ext = Path(video["filename"]).suffix
    stem = Path(video["filename"]).stem

    # 2. Validate times and get duration
    duration = await _get_video_duration(video_path)
    _validate_times(start_time, end_time, duration)

    # Prevent removing the entire video
    if start_time <= 0 and end_time >= (duration or 0):
        raise ValueError("Cannot remove the entire video.")

    # Determine which segments to keep
    has_before = start_time > 0
    has_after = end_time < (duration or 0)

    tmp_path = video_path.with_name(f"{stem}_cut_tmp{ext}")

    try:
        if has_before and has_after:
            # ── Middle cut: re-encode via trim + concat filters ─────
            has_audio = await _has_audio_stream(video_path)

            if has_audio:
                filter_complex = ";".join(
                    [
                        f"[0:v]trim=0:{start_time},setpts=PTS-STARTPTS[v0]",
                        f"[0:v]trim={end_time}:{duration},setpts=PTS-STARTPTS[v1]",
                        f"[v0][v1]concat=n=2:v=1:a=0[vout]",
                        f"[0:a]atrim=0:{start_time},asetpts=PTS-STARTPTS[a0]",
                        f"[0:a]atrim={end_time}:{duration},asetpts=PTS-STARTPTS[a1]",
                        f"[a0][a1]concat=n=2:v=0:a=1[aout]",
                    ]
                )
                maps = ["-map", "[vout]", "-map", "[aout]"]
            else:
                filter_complex = ";".join(
                    [
                        f"[0:v]trim=0:{start_time},setpts=PTS-STARTPTS[v0]",
                        f"[0:v]trim={end_time}:{duration},setpts=PTS-STARTPTS[v1]",
                        f"[v0][v1]concat=n=2:v=1:a=0[vout]",
                    ]
                )
                maps = ["-map", "[vout]"]

            await _run_ffmpeg(
                [
                    "-i",
                    str(video_path),
                    "-filter_complex",
                    filter_complex,
                    *maps,
                    str(tmp_path),
                ]
            )

        elif has_before:
            # ── Trim end only: keep [0, start_time) ─────────────────
            has_audio = await _has_audio_stream(video_path)
            if has_audio:
                await _run_ffmpeg(
                    [
                        "-i", str(video_path),
                        "-filter_complex",
                        f"[0:v]trim=0:{start_time},setpts=PTS-STARTPTS[vout];"
                        f"[0:a]atrim=0:{start_time},asetpts=PTS-STARTPTS[aout]",
                        "-map", "[vout]", "-map", "[aout]",
                        str(tmp_path),
                    ]
                )
            else:
                await _run_ffmpeg(
                    [
                        "-i", str(video_path),
                        "-filter_complex",
                        f"[0:v]trim=0:{start_time},setpts=PTS-STARTPTS[vout]",
                        "-map", "[vout]",
                        str(tmp_path),
                    ]
                )

        else:
            # ── Trim start only: keep [end_time, duration) ─────────
            has_audio = await _has_audio_stream(video_path)
            if has_audio:
                await _run_ffmpeg(
                    [
                        "-i", str(video_path),
                        "-filter_complex",
                        f"[0:v]trim={end_time}:{duration},setpts=PTS-STARTPTS[vout];"
                        f"[0:a]atrim={end_time}:{duration},asetpts=PTS-STARTPTS[aout]",
                        "-map", "[vout]", "-map", "[aout]",
                        str(tmp_path),
                    ]
                )
            else:
                await _run_ffmpeg(
                    [
                        "-i", str(video_path),
                        "-filter_complex",
                        f"[0:v]trim={end_time}:{duration},setpts=PTS-STARTPTS[vout]",
                        "-map", "[vout]",
                        str(tmp_path),
                    ]
                )

        if not tmp_path.exists():
            raise RuntimeError("ffmpeg completed but output file was not created.")

        # 3. Replace original with trimmed version (atomic on same filesystem)
        tmp_path.replace(video_path)

        new_size = video_path.stat().st_size

        # 4. Update DB
        await db.execute(
            "UPDATE videos SET file_size = ? WHERE id = ?",
            (new_size, video_id),
        )
        await db.commit()

        # 5. Regenerate thumbnail
        await file_service.generate_thumbnail(video["filename"])

    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    logger.info(
        "Video cut: id=%d removed [%.1fs-%.1fs]",
        video_id,
        start_time,
        end_time,
    )
    return await video_service.get_video(db, video_id)


# ── Public API ───────────────────────────────────────────────────


async def create_clip(
    db: aiosqlite.Connection,
    source_video_id: int,
    start_time: float,
    end_time: float,
) -> dict:
    """Extract a clip from a source video and return the new video record.

    Steps:
    1. Fetch source video metadata from DB
    2. Validate time bounds (start < end, >= 1s, within duration)
    3. Generate unique clip filename
    4. Run ffmpeg to cut the clip
    5. Generate thumbnail from the clip's first frame
    6. Create new video DB record with source_video_id, clip_start, clip_end
    7. Copy source video tags to the clip
    8. Return the new video dict
    """
    # 1. Fetch source video
    source = await video_service.get_video(db, source_video_id)
    if source is None:
        raise ValueError(f"Source video with id {source_video_id} not found.")

    source_path = file_service.get_video_path(source["filename"])

    # 2. Validate times
    duration = await _get_video_duration(source_path)
    _validate_times(start_time, end_time, duration)

    # 3. Generate clip filename
    clip_duration = end_time - start_time
    clip_filename = _generate_clip_filename(source["filename"], start_time, end_time)
    clip_path = file_service.get_video_path(clip_filename)

    # 4. Run ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found. Install with: sudo apt install ffmpeg")

    # NOTE: -c copy uses stream copy (fast but keyframe-aligned).
    # For frame-accurate cuts, replace with re-encode:
    #   "-c:v", "libx264", "-c:a", "aac",
    #   "-avoid_negative_ts", "1"
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-ss",
        f"{start_time:.3f}",
        "-i",
        str(source_path),
        "-t",
        f"{clip_duration:.3f}",
        "-c",
        "copy",
        str(clip_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown ffmpeg error"
        # Clean up partial output on failure
        if clip_path.exists():
            clip_path.unlink()
        logger.error(
            "ffmpeg failed for clip from video %d: %s",
            source_video_id,
            error_msg,
        )
        raise RuntimeError(f"ffmpeg failed: {error_msg}")

    if not clip_path.exists():
        raise RuntimeError("ffmpeg completed but output file was not created.")

    # 5. Generate thumbnail
    await file_service.generate_thumbnail(clip_filename)

    # 6. Create DB record and copy tags within a transaction
    try:
        cursor = await db.execute(
            """INSERT INTO videos (name, filename, original_name, mime_type, file_size,
                                   source_video_id, clip_start, clip_end)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"{source['name']} (clip)",
                clip_filename,
                clip_filename,
                source["mime_type"],
                clip_path.stat().st_size,
                source_video_id,
                start_time,
                end_time,
            ),
        )
        clip_id = cursor.lastrowid

        # 7. Copy source video tags
        source_tags = await tag_service.get_video_tags(db, source_video_id)
        if source_tags:
            await tag_service.set_video_tags(db, clip_id, source_tags)

        await db.commit()
    except Exception:
        await db.rollback()
        # Clean up the created file on failure
        if clip_path.exists():
            clip_path.unlink()
        raise

    # 8. Return new video
    logger.info(
        "Clip created: id=%d from video=%d [%.1fs-%.1fs]",
        clip_id,
        source_video_id,
        start_time,
        end_time,
    )
    return await video_service.get_video(db, clip_id)
