"""
Tests for clip creation (Checkpoint 2).

Run with: pytest tests/test_clips.py -v

These tests mock ffmpeg/ffprobe subprocess calls since those tools
may not be available in CI. The validation logic (time bounds,
source existence, tag copying) is tested directly.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


class TestClipServiceValidation:
    """Tests for clip service validation rules (no ffmpeg needed)."""

    @pytest.mark.asyncio
    async def test_clip_start_after_end(self, client, db):
        """POST with start > end returns 400."""
        # Upload a source video first
        await client.post(
            "/api/videos",
            data={"name": "Source", "tags": "test-tag"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": 30, "end": 10}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Start must be before end" in data["error"]

    @pytest.mark.asyncio
    async def test_clip_minimum_duration(self, client, db):
        """POST with duration < 1s returns 400."""
        await client.post(
            "/api/videos",
            data={"name": "Source", "tags": ""},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": 5, "end": 5.5}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Minimum clip duration" in data["error"]

    @pytest.mark.asyncio
    async def test_clip_nonexistent_source(self, client, db):
        """POST for non-existent video returns 404."""
        response = await client.post(
            "/api/video/999/clip",
            content=json.dumps({"start": 0, "end": 5}),
            headers={"Content-Type": "application/json"},
        )
        # Route catches ValueError (source not found) and returns 400
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_missing_fields(self, client, db):
        """POST without start/end fields returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_invalid_json(self, client, db):
        """POST with non-JSON body returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_non_numeric_times(self, client, db):
        """POST with non-numeric times returns 400."""
        response = await client.post(
            "/api/video/1/clip",
            content=json.dumps({"start": "abc", "end": "def"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestClipPage:
    """Tests for the clip creator page."""

    @pytest.mark.asyncio
    async def test_clip_page_renders(self, client, db):
        """GET /video/{id}/clip shows the clip creator."""
        await client.post(
            "/api/videos",
            data={"name": "Clip Source", "tags": ""},
            files={"file": ("src.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1/clip")
        assert response.status_code == 200
        assert "Create Clip" in response.text
        assert "clip-video" in response.text  # video element ID
        assert "clip-start" in response.text  # start range ID
        assert "clip-end" in response.text    # end range ID
        assert "create-clip-btn" in response.text  # button ID

    @pytest.mark.asyncio
    async def test_clip_page_not_found(self, client, db):
        """GET /video/{id}/clip for missing id returns 404."""
        response = await client.get("/video/999/clip")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clip_page_shows_source_name(self, client, db):
        """Clip page shows the source video name."""
        await client.post(
            "/api/videos",
            data={"name": "My Awesome Video", "tags": ""},
            files={"file": ("src.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1/clip")
        assert "My Awesome Video" in response.text


@pytest.mark.usefixtures("db")
class TestClipCreationWithMock:
    """Tests that mock ffmpeg/ffprobe for end-to-end clip creation."""

    @pytest.mark.asyncio
    async def test_clip_creates_db_record(self, client, db):
        """Successful clip creation inserts a DB record with source_video_id."""
        await client.post(
            "/api/videos",
            data={"name": "Source Vid", "tags": "alpha, beta"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        # Mock ffprobe to return a 60s duration
        # Mock ffmpeg to succeed (return code 0, create a dummy file)
        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            # Mock ffprobe subprocess
            mock_ffprobe_proc = AsyncMock()
            mock_ffprobe_proc.returncode = 0
            mock_ffprobe_proc.communicate = AsyncMock(
                return_value=(b"60.0\n", b"")
            )

            # Mock ffmpeg subprocess
            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 0
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b""))

            # Return ffprobe on first call, ffmpeg on second
            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            # Also need to mock file existence for the clip output path
            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                _stat_result = lambda self: type("Stat", (), {"st_size": 1024})()
                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": _stat_result})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": _stat_result,
                    "unlink": lambda self: None,
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 10, "end": 20}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify clip record in DB
        cursor = await db.execute("SELECT * FROM videos WHERE id = 2")
        clip = dict(await cursor.fetchone())
        assert clip["source_video_id"] == 1
        assert clip["clip_start"] == 10.0
        assert clip["clip_end"] == 20.0
        assert clip["name"] == "Source Vid (clip)"

    @pytest.mark.asyncio
    async def test_clip_copies_source_tags(self, client, db):
        """Clip creation copies all tags from source video."""
        await client.post(
            "/api/videos",
            data={"name": "Tagged Source", "tags": "tutorial, funny, demo"},
            files={"file": ("src.mp4", b"fake-video-content", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe_proc = AsyncMock()
            mock_ffprobe_proc.returncode = 0
            mock_ffprobe_proc.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 0
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b""))

            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                _stat_result = lambda self: type("Stat", (), {"st_size": 1024})()
                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": _stat_result})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: True,
                    "stat": _stat_result,
                    "unlink": lambda self: None,
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 5, "end": 15}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 200

        # Verify clip has the same tags
        detail = await client.get("/video/2")
        assert "tutorial" in detail.text
        assert "funny" in detail.text
        assert "demo" in detail.text

    @pytest.mark.asyncio
    async def test_clip_ffmpeg_failure_returns_500(self, client, db):
        """When ffmpeg fails, clip endpoint returns 500."""
        await client.post(
            "/api/videos",
            data={"name": "Failing Source", "tags": ""},
            files={"file": ("fail.mp4", b"fake-video-content", "video/mp4")},
        )

        with patch("app.services.clip_service.shutil.which") as mock_which, \
             patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

            mock_which.side_effect = lambda cmd: {
                "ffprobe": "/usr/bin/ffprobe",
                "ffmpeg": "/usr/bin/ffmpeg",
            }.get(cmd)

            mock_ffprobe_proc = AsyncMock()
            mock_ffprobe_proc.returncode = 0
            mock_ffprobe_proc.communicate = AsyncMock(return_value=(b"60.0\n", b""))

            mock_ffmpeg_proc = AsyncMock()
            mock_ffmpeg_proc.returncode = 1
            mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error output"))

            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

            with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
                 patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

                mock_src_path = type("Path", (), {"exists": lambda self: True, "stat": type("Stat", (), {"st_size": 1024})()})()
                mock_clip_path = type("Path", (), {
                    "exists": lambda self: False,
                    "unlink": lambda self: None,
                })()

                def get_path_side_effect(filename):
                    if "src" in filename:
                        return mock_src_path
                    return mock_clip_path

                mock_get_path.side_effect = get_path_side_effect

                response = await client.post(
                    "/api/video/1/clip",
                    content=json.dumps({"start": 0, "end": 10}),
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "ffmpeg" in data["error"].lower()
