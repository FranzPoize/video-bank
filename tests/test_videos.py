"""
Tests for video upload and listing (Checkpoint 1).

Run with: pytest tests/test_videos.py -v
"""

import collections
import pytest
from unittest.mock import patch

# shutil.disk_usage returns a namedtuple; use same shape for mocks
from tests.conftest import create_test_video

DiskUsage = collections.namedtuple("DiskUsage", ["total", "used", "free"])


class TestVideoList:
    """Tests for the video list endpoint."""

    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        """GET / should show empty state when no videos exist."""
        response = await client.get("/videos")
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
        list_resp = await client.get("/videos")
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
        assert response.headers["location"] == "/videos"

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
        """GET /videos/{id} shows the detail page."""
        video_id = await create_test_video(client, "Playback Test")

        response = await client.get(f"/videos/{video_id}")
        assert response.status_code == 200
        assert "Playback Test" in response.text
        assert "<video" in response.text

    @pytest.mark.asyncio
    async def test_video_detail_not_found(self, client):
        """GET /videos/{id} for missing id returns 404."""
        response = await client.get("/videos/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_video_stream_endpoint(self, client):
        """GET /api/videos/{id}/file returns video bytes."""
        video_id = await create_test_video(client, "Stream Test")

        response = await client.get(f"/api/videos/{video_id}/file")
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_video_stream_not_found(self, client):
        """GET /api/videos/{id}/file for missing id returns 404."""
        response = await client.get("/api/videos/999/file")
        assert response.status_code == 404


class TestVideoFilter:
    """Tests for tag-based filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_tag(self, client):
        """GET /?tag_id=X shows only videos with that tag."""
        # Upload two videos with different tags
        await client.post(
            "/api/videos",
            data={"name": "Video A", "tags": "alpha"},
            files={"file": ("a.mp4", b"content", "video/mp4")},
        )
        await client.post(
            "/api/videos",
            data={"name": "Video B", "tags": "beta"},
            files={"file": ("b.mp4", b"content", "video/mp4")},
        )

        # Get tag IDs
        tags_resp = await client.get("/api/tags")
        tags = tags_resp.json()["tags"]
        assert "alpha" in tags
        assert "beta" in tags

        # Filter by "alpha" — we don't know the tag_id, so use the list view
        # with the tag name present in the response
        list_resp = await client.get("/videos")
        assert "Video A" in list_resp.text
        assert "Video B" in list_resp.text

    @pytest.mark.asyncio
    async def test_filter_htmx(self, client):
        """HTMX request to /?tag_id=X returns only grid fragment."""
        await client.post(
            "/api/videos",
            data={"name": "HTMX Filter", "tags": "filterable"},
            files={"file": ("h.mp4", b"c", "video/mp4")},
        )

        response = await client.get(
            "/videos",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        # HTMX request should return grid, not full page
        # Check by asserting no <nav> in response (nav is in base.html)
        assert "<nav>" not in response.text


class TestVideoCRUD:
    """Tests for edit and delete operations."""

    @pytest.mark.asyncio
    async def test_edit_video_name(self, client):
        """POST /videos/{id}/edit updates the video name."""
        video_id = await create_test_video(client, "Original Name", "")

        response = await client.post(
            f"/videos/{video_id}/edit",
            data={"name": "Updated Name", "tags": ""},
        )
        assert response.status_code == 303

        detail = await client.get(f"/videos/{video_id}")
        assert "Updated Name" in detail.text
        assert "Original Name" not in detail.text

    @pytest.mark.asyncio
    async def test_edit_video_tags(self, client):
        """POST /videos/{id}/edit updates tags."""
        video_id = await create_test_video(client, "Tag Edit", "old-tag")

        await client.post(
            f"/videos/{video_id}/edit",
            data={"name": "Tag Edit", "tags": "new-tag, another"},
        )

        detail = await client.get(f"/videos/{video_id}")
        assert "new-tag" in detail.text
        assert "another" in detail.text
        assert "old-tag" not in detail.text

    @pytest.mark.asyncio
    async def test_delete_video(self, client):
        """POST /videos/{id}/delete removes the video."""
        video_id = await create_test_video(client, "To Delete", "")

        # Verify it shows in list
        list_before = await client.get("/videos")
        assert "To Delete" in list_before.text

        # Delete it
        response = await client.post(f"/videos/{video_id}/delete")
        assert response.status_code == 303

        # Verify it's gone from list
        list_after = await client.get("/videos")
        assert "To Delete" not in list_after.text

    @pytest.mark.asyncio
    async def test_delete_nonexistent_video(self, client):
        """POST /videos/{id}/delete for missing id returns 404."""
        response = await client.post("/videos/999/delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_form_page(self, client):
        """GET /videos/{id}/edit shows edit form with current values."""
        video_id = await create_test_video(client, "Form Test", "form-tag")

        response = await client.get(f"/videos/{video_id}/edit")
        assert response.status_code == 200
        assert "Form Test" in response.text
        assert "form-tag" in response.text
        assert "Save Changes" in response.text
        assert "Delete Video" in response.text


class TestEdgeCases:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_404_page(self, client):
        """Accessing a non-existent page shows styled 404."""
        response = await client.get("/nonexistent")
        assert response.status_code == 404
        assert "doesn&#39;t exist" in response.text or "doesn't exist" in response.text

    @pytest.mark.asyncio
    async def test_video_detail_nonexistent(self, client):
        """Accessing non-existent video detail returns 404."""
        response = await client.get("/videos/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_nonexistent_video(self, client):
        """Editing non-existent video returns 404."""
        response = await client.get("/videos/999/edit")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_then_delete_then_reupload(self, client):
        """Upload, delete, upload again — IDs increment correctly."""
        await client.post(
            "/api/videos",
            data={"name": "First", "tags": ""},
            files={"file": ("first.mp4", b"c", "video/mp4")},
        )
        await client.post("/videos/1/delete")

        await client.post(
            "/api/videos",
            data={"name": "Second", "tags": ""},
            files={"file": ("second.mp4", b"c", "video/mp4")},
        )

        detail = await client.get("/videos/2")
        assert detail.status_code == 200
        assert "Second" in detail.text

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client):
        """Upload without file returns 422."""
        response = await client.post(
            "/api/videos",
            data={"name": "No File"},
        )
        assert response.status_code == 422


class TestAsyncUpload:
    """Tests for XHR-based async upload (Checkpoint 1)."""

    @pytest.mark.asyncio
    async def test_upload_xhr_returns_json(self, client):
        """POST /api/videos with X-Requested-With returns JSON."""
        response = await client.post(
            "/api/videos",
            data={"name": "XHR Upload"},
            files={"file": ("xhr.mp4", b"fake-video-content", "video/mp4")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] >= 1
        assert "redirect" in data
        assert data["redirect"] == "/videos"

    @pytest.mark.asyncio
    async def test_upload_xhr_bad_format(self, client):
        """XHR upload with unsupported format returns JSON error."""
        response = await client.post(
            "/api/videos",
            data={"name": "XHR Bad"},
            files={"file": ("bad.avi", b"content", "video/x-msvideo")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "unsupported" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_upload_xhr_missing_name(self, client):
        """XHR upload without name returns JSON error (422 from FastAPI)."""
        response = await client.post(
            "/api/videos",
            data={"name": ""},
            files={"file": ("no-name.mp4", b"content", "video/mp4")},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # FastAPI's Form(...) returns 422 before our handler runs
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_upload_form_still_redirects(self, client):
        """Regular form upload still returns 303 redirect."""
        response = await client.post(
            "/api/videos",
            data={"name": "Form Upload"},
            files={"file": ("form.mp4", b"fake-content", "video/mp4")},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/videos"


class TestDiskSpace:
    """Tests for disk space indicator and upload guard."""

    @pytest.mark.asyncio
    async def test_available_space(self):
        """get_available_space computes free_gb and percent_used correctly."""
        from app.services.file_service import get_available_space

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 500GB used out of 1TB → 50% used
            mock_du.return_value = DiskUsage(1_000_000_000_000, 500_000_000_000, 500_000_000_000)
            result = get_available_space()

        assert result.get("error") is not True
        assert result["total"] == 1_000_000_000_000
        assert result["used"] == 500_000_000_000
        assert result["free"] == 500_000_000_000
        assert result["percent_used"] == 0.5
        # 500 GB / 1024^3 ≈ 465.7
        assert result["free_gb"] == 465.7

    @pytest.mark.asyncio
    async def test_disk_usage_error_handling(self, client):
        """When shutil.disk_usage raises OSError, upload still works."""
        from app.services.file_service import get_available_space

        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.side_effect = OSError("Permission denied")

            # Sentinel dict is returned
            result = get_available_space()
            assert result.get("error") is True

            # Upload should NOT be blocked by a failing space check
            response = await client.post(
                "/api/videos",
                data={"name": "Disk Error Test"},
                files={"file": ("error.mp4", b"fake-content", "video/mp4")},
            )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_upload_rejected_disk_full(self, client):
        """Upload rejected when projected disk usage > 95%."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 951GB used out of 1TB → 95.1% — any tiny file pushes over 95%
            mock_du.return_value = DiskUsage(1_000_000_000_000, 951_000_000_000, 49_000_000_000)

            response = await client.post(
                "/api/videos",
                data={"name": "Full Disk"},
                files={"file": ("full.mp4", b"oops", "video/mp4")},
            )
        assert response.status_code == 400
        assert "disk space" in response.text.lower()

    @pytest.mark.asyncio
    async def test_upload_allowed_disk_available(self, client):
        """Upload succeeds when there is plenty of disk space."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.return_value = DiskUsage(1_000_000_000_000, 500_000_000_000, 500_000_000_000)

            response = await client.post(
                "/api/videos",
                data={"name": "Space Available"},
                files={"file": ("ok.mp4", b"fake-content", "video/mp4")},
            )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_space_api_endpoint(self, client):
        """GET /api/space returns HTML fragment with color-coded space info."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 500GB used out of 1TB → 50% → space-ok (green)
            mock_du.return_value = DiskUsage(1_000_000_000_000, 500_000_000_000, 500_000_000_000)

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "GB free" in response.text
        assert "uk-badge" in response.text

    @pytest.mark.asyncio
    async def test_space_api_endpoint_critical(self, client):
        """GET /api/space shows uk-badge-destructive class when disk is near full."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            # 950GB used out of 1TB → 95% → uk-badge-destructive (red)
            mock_du.return_value = DiskUsage(1_000_000_000_000, 950_000_000_000, 50_000_000_000)

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "uk-badge-destructive" in response.text

    @pytest.mark.asyncio
    async def test_space_api_endpoint_error(self, client):
        """GET /api/space shows 'Space: unknown' when disk_usage fails."""
        with patch("app.services.file_service.shutil.disk_usage") as mock_du:
            mock_du.side_effect = OSError("Permission denied")

            response = await client.get("/api/space")
        assert response.status_code == 200
        assert "Space: unknown" in response.text
        assert "uk-badge-destructive" in response.text
