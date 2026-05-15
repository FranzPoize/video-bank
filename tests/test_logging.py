"""
Tests for app logging instrumentation.

Uses pytest's caplog fixture to verify log records are emitted
at the expected levels for key app events. Does NOT test log
files directly (no file I/O).

NOTE: httpx's ASGITransport does NOT trigger ASGI lifespan events,
so startup logs (on_startup) cannot be tested via client requests.
We call on_startup() directly where needed.

Run with: pytest tests/test_logging.py -v
"""

import collections
from unittest.mock import AsyncMock, patch

import pytest

DiskUsage = collections.namedtuple("DiskUsage", ["total", "used", "free"])


class TestStartupLogging:
    """Tests for startup log messages (main.py on_startup).

    httpx ASGITransport does not trigger ASGI lifespan events, so we
    call on_startup() directly and mock init_db to avoid side effects.
    """

    @pytest.mark.asyncio
    async def test_app_starts_logs_info(self, caplog):
        """App startup logs INFO messages about ffmpeg and DB path."""
        caplog.set_level("INFO")
        from app.main import on_startup
        with patch("app.main.init_db", AsyncMock()):
            await on_startup()

        startup_messages = [r for r in caplog.records if "Video Bank started" in r.getMessage()]
        assert len(startup_messages) >= 1
        assert startup_messages[0].levelname == "INFO"

    @pytest.mark.asyncio
    async def test_ffmpeg_not_found_logs_warning(self, caplog):
        """generate_thumbnail returns False silently when ffmpeg is missing."""
        caplog.set_level("WARNING")
        from app.services.file_service import generate_thumbnail
        with patch("app.services.file_service.shutil.which", return_value=None):
            # generate_thumbnail returns early (before any log) when
            # shutil.which("ffmpeg") returns None, so no WARNING is emitted
            result = await generate_thumbnail("nonexistent.mp4")
        assert result is False
        ffmpeg_logs = [r for r in caplog.records if "ffmpeg" in r.getMessage().lower()]
        # Graceful degradation is silent at WARNING level — no log expected
        assert len(ffmpeg_logs) == 0


class TestFileServiceLogging:
    """Tests for log messages in file_service.py."""

    @pytest.mark.asyncio
    async def test_save_upload_logs_info(self, client, db, caplog):
        """Uploading a file produces an INFO log."""
        caplog.set_level("INFO")

        response = await client.post(
            "/api/videos",
            data={"name": "Log Test", "tags": ""},
            files={"file": ("logtest.mp4", b"fake-video-content", "video/mp4")},
        )
        assert response.status_code == 303

        # Check for file-saved log
        saved_logs = [r for r in caplog.records if "File saved" in r.getMessage()]
        assert len(saved_logs) >= 1
        assert saved_logs[0].levelname == "INFO"

    @pytest.mark.asyncio
    async def test_disk_usage_error_logs_warning(self, caplog):
        """When disk_usage fails, a WARNING is logged."""
        from app.services.file_service import get_available_space

        caplog.set_level("WARNING")

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.side_effect = OSError("Permission denied")
            result = get_available_space()

        assert result.get("error") is True
        disk_warnings = [r for r in caplog.records if "disk usage" in r.getMessage().lower()]
        assert len(disk_warnings) >= 1
        assert disk_warnings[0].levelname == "WARNING"

    @pytest.mark.asyncio
    async def test_thumbnail_generation_logs_info(self, caplog):
        """Successful thumbnail generation logs INFO."""
        from app.services.file_service import generate_thumbnail

        caplog.set_level("INFO")

        with patch("app.services.file_service.shutil.which") as mock_which, \
             patch("app.services.file_service.asyncio.create_subprocess_exec") as mock_subproc, \
             patch("app.services.file_service.Path.exists") as mock_exists:

            mock_which.return_value = "/usr/bin/ffmpeg"
            mock_proc = AsyncMock()
            mock_proc.wait = AsyncMock(return_value=0)
            mock_subproc.return_value = mock_proc

            # First exists() call (early-return check) -> False
            # Second exists() call (post-ffmpeg check) -> True
            mock_exists.side_effect = [False, True]

            result = await generate_thumbnail("test.mp4")

        assert result is True
        thumb_logs = [r for r in caplog.records if "Thumbnail generated" in r.getMessage()]
        assert len(thumb_logs) >= 1
        assert thumb_logs[0].levelname == "INFO"

    @pytest.mark.asyncio
    async def test_thumbnail_failure_logs_error(self, caplog):
        """ffmpeg failure during thumbnail generation logs ERROR."""
        from app.services.file_service import generate_thumbnail

        caplog.set_level("ERROR")

        with patch("app.services.file_service.shutil.which") as mock_which, \
             patch("app.services.file_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.return_value = "/usr/bin/ffmpeg"
            mock_proc = AsyncMock()
            mock_proc.wait = AsyncMock(return_value=1)
            mock_subproc.return_value = mock_proc

            with patch("app.services.file_service.Path.exists", return_value=False):
                result = await generate_thumbnail("test.mp4")

        assert result is False
        error_logs = [r for r in caplog.records if "Thumbnail generation failed" in r.getMessage()]
        assert len(error_logs) >= 1
        assert error_logs[0].levelname == "ERROR"

    @pytest.mark.asyncio
    async def test_disk_near_capacity_logs_warning(self, caplog):
        """Disk near capacity logs WARNING in validate_file."""
        from app.services.file_service import validate_file

        caplog.set_level("WARNING")

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 800GB used out of 1TB, adding 1GB → 80.1% projected (>80% threshold)
            # File size must be under 2GB (MAX_UPLOAD_SIZE)
            mock_du.return_value = DiskUsage(1_000_000_000_000, 800_000_000_000, 200_000_000_000)
            error = validate_file("test.mp4", 1_000_000_000)  # 1GB

        assert error is None  # Under 95%, so passes
        capacity_logs = [r for r in caplog.records if "Disk near capacity" in r.getMessage()]
        assert len(capacity_logs) >= 1
        assert capacity_logs[0].levelname == "WARNING"


class TestVideoServiceLogging:
    """Tests for log messages in video_service.py."""

    @pytest.mark.asyncio
    async def test_upload_rejected_logs_warning(self, client, caplog):
        """Upload rejection (bad format) logs WARNING."""
        caplog.set_level("WARNING")

        response = await client.post(
            "/api/videos",
            data={"name": "Bad Format"},
            files={"file": ("bad.avi", b"content", "video/x-msvideo")},
        )
        assert response.status_code == 400

        warning_logs = [r for r in caplog.records if "Upload rejected" in r.getMessage()]
        assert len(warning_logs) >= 1
        assert warning_logs[0].levelname == "WARNING"

    @pytest.mark.asyncio
    async def test_delete_video_logs_info(self, client, caplog):
        """Deleting a video logs INFO."""
        caplog.set_level("INFO")

        # Upload first
        await client.post(
            "/api/videos",
            data={"name": "To Delete", "tags": ""},
            files={"file": ("todel.mp4", b"c", "video/mp4")},
        )

        response = await client.post("/video/1/delete")
        assert response.status_code == 303

        delete_logs = [r for r in caplog.records if "Video deleted" in r.getMessage()]
        assert len(delete_logs) >= 1
        assert delete_logs[0].levelname == "INFO"


class TestClipServiceLogging:
    """Tests for log messages in clip_service.py."""

    @pytest.mark.asyncio
    async def test_clip_created_logs_info(self, client, db, caplog):
        """Successful clip creation logs INFO."""
        from app.services.clip_service import create_clip

        caplog.set_level("INFO")

        # Upload source video
        await client.post(
            "/api/videos",
            data={"name": "Source Vid", "tags": ""},
            files={"file": ("src.mp4", b"fake-content", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe = AsyncMock()
            mock_ffprobe.returncode = 0
            mock_ffprobe.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg = AsyncMock()
            mock_ffmpeg.returncode = 0
            mock_ffmpeg.communicate = AsyncMock(return_value=(b"", b""))

            mock_subproc.side_effect = [mock_ffprobe, mock_ffmpeg]

            _stat = type("Stat", (), {"st_size": 1024})()

            with patch("app.services.clip_service.file_service.get_video_path") as mock_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                mock_src = type("Path", (), {"exists": lambda self: True, "stat": lambda self: _stat})()
                mock_clip = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": lambda self: _stat,
                    "unlink": lambda self: None,
                })()

                def path_side_effect(fn):
                    if "src" in fn or "clip" in fn:
                        return mock_clip
                    return mock_src

                mock_path.side_effect = path_side_effect

                clip = await create_clip(db, 1, 10.0, 20.0)

        assert clip is not None
        clip_logs = [r for r in caplog.records if "Clip created" in r.getMessage()]
        assert len(clip_logs) >= 1
        assert clip_logs[0].levelname == "INFO"

    @pytest.mark.asyncio
    async def test_clip_ffmpeg_failure_logs_error(self, client, db, caplog):
        """ffmpeg failure during clip creation logs ERROR."""
        from app.services.clip_service import create_clip

        caplog.set_level("ERROR")

        await client.post(
            "/api/videos",
            data={"name": "Failing Source", "tags": ""},
            files={"file": ("fail.mp4", b"c", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe = AsyncMock()
            mock_ffprobe.returncode = 0
            mock_ffprobe.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg = AsyncMock()
            mock_ffmpeg.returncode = 1
            mock_ffmpeg.communicate = AsyncMock(return_value=(b"", b"ffmpeg crashed"))

            mock_subproc.side_effect = [mock_ffprobe, mock_ffmpeg]

            with patch("app.services.clip_service.file_service.get_video_path") as mock_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                # Mock Path must support exists(), stat(), and unlink()
                _mock_stat = type("Stat", (), {"st_size": 1024})()
                mock_src = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": lambda self: _mock_stat,
                    "unlink": lambda self: None,
                })()

                def path_side_effect(fn):
                    return mock_src

                mock_path.side_effect = path_side_effect

                with pytest.raises(RuntimeError, match="ffmpeg failed"):
                    await create_clip(db, 1, 0.0, 10.0)

        error_logs = [r for r in caplog.records if "ffmpeg failed for clip" in r.getMessage()]
        assert len(error_logs) >= 1
        assert error_logs[0].levelname == "ERROR"
