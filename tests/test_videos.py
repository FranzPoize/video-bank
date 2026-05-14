"""
Tests for video upload and listing (Checkpoint 1).

Run with: pytest tests/test_videos.py -v
"""

import pytest


class TestVideoList:
    """Tests for the video list endpoint."""

    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        """GET / should show empty state when no videos exist."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "No videos yet" in response.text

    @pytest.mark.asyncio
    async def test_list_after_upload(self, client):
        """GET / should show uploaded video."""
        # Upload a video first
        upload_resp = await client.post(
            "/api/videos",
            data={"name": "Test Video"},
            files={"file": ("test.mp4", b"fake-video-content", "video/mp4")},
        )
        assert upload_resp.status_code == 303  # redirect

        # Now list should show it
        list_resp = await client.get("/")
        assert list_resp.status_code == 200
        assert "Test Video" in list_resp.text


class TestVideoUpload:
    """Tests for the upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_success(self, client):
        """POST /api/videos with valid data redirects to list."""
        response = await client.post(
            "/api/videos",
            data={"name": "My Clip"},
            files={"file": ("clip.mp4", b"fake-video-content", "video/mp4")},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_upload_creates_db_record(self, client, db):
        """Upload inserts a row into the database."""
        await client.post(
            "/api/videos",
            data={"name": "DB Test"},
            files={"file": ("db.mp4", b"some-content", "video/mp4")},
        )
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    @pytest.mark.asyncio
    async def test_upload_requires_name(self, client):
        """Upload without name should fail."""
        response = await client.post(
            "/api/videos",
            data={"name": ""},
            files={"file": ("no-name.mp4", b"content", "video/mp4")},
        )
        # FastAPI's Form(...) returns 422 for missing required fields
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_unsupported_format(self, client):
        """Upload with unsupported extension returns 400."""
        response = await client.post(
            "/api/videos",
            data={"name": "Bad Format"},
            files={"file": ("bad.avi", b"content", "video/x-msvideo")},
        )
        assert response.status_code == 400
        assert "unsupported" in response.text.lower()

    @pytest.mark.asyncio
    async def test_upload_form_page(self, client):
        """GET /upload shows the upload form."""
        response = await client.get("/upload")
        assert response.status_code == 200
        assert "Upload" in response.text


class TestVideoPlayback:
    """Tests for video streaming and detail page."""

    @pytest.mark.asyncio
    async def test_video_detail_page(self, client):
        """GET /video/{id} shows the detail page."""
        # Upload first
        await client.post(
            "/api/videos",
            data={"name": "Playback Test"},
            files={"file": ("play.mp4", b"fake-content", "video/mp4")},
        )

        response = await client.get("/video/1")
        assert response.status_code == 200
        assert "Playback Test" in response.text
        assert "<video" in response.text

    @pytest.mark.asyncio
    async def test_video_detail_not_found(self, client):
        """GET /video/{id} for missing id returns 404."""
        response = await client.get("/video/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_video_stream_endpoint(self, client):
        """GET /api/video/{id}/file returns video bytes."""
        await client.post(
            "/api/videos",
            data={"name": "Stream Test"},
            files={"file": ("stream.mp4", b"fake-video-content", "video/mp4")},
        )

        response = await client.get("/api/video/1/file")
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_video_stream_not_found(self, client):
        """GET /api/video/{id}/file for missing id returns 404."""
        response = await client.get("/api/video/999/file")
        assert response.status_code == 404
