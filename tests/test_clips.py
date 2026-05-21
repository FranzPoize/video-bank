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

from tests.conftest import mock_ffmpeg, create_test_video
from app.services import clip_service, tag_service, video_service


async def _create_account(db, name: str) -> int:
    """Create a minimal account row for account-scoped clip service tests."""
    cursor = await db.execute("INSERT INTO accounts (display_name) VALUES (?)", (name,))
    await db.commit()
    return cursor.lastrowid


async def _create_service_video(db, account_id: int, name: str, tags: str = "") -> dict:
    """Create a video through the service without touching real storage."""
    with patch("app.services.video_service.file_service.save_upload", AsyncMock(return_value=f"{name}.mp4")), \
         patch("app.services.video_service.file_service.generate_thumbnail", AsyncMock(return_value=False)):
        return await video_service.create_video(
            db,
            name=name,
            file_content=b"video",
            original_name=f"{name}.mp4",
            mime_type="video/mp4",
            file_size=5,
            account_id=account_id,
            tags=tags,
        )


class TestClipServiceValidation:
    """Tests for clip service validation rules (no ffmpeg needed)."""

    @pytest.mark.asyncio
    async def test_clip_start_after_end(self, client, db):
        """POST with start > end returns 400."""
        video_id = await create_test_video(client, "Source", "test-tag")

        response = await client.post(
            f"/api/videos/{video_id}/clip",
            content=json.dumps({"start": 30, "end": 10}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Start must be before end" in data["error"]


class TestClipServiceAccountIsolation:
    """Service-level tests for account-scoped clip and cut operations."""

    @pytest.mark.asyncio
    async def test_clip_cross_account_source_behaves_not_found(self, db):
        """Creating a clip from another account's source raises safe not-found ValueError."""
        account_one = await _create_account(db, "Team One")
        account_two = await _create_account(db, "Team Two")
        source = await _create_service_video(db, account_one, "Source", "alpha")

        with pytest.raises(ValueError, match="Source video with id"):
            await clip_service.create_clip(
                db,
                source["id"],
                1,
                5,
                account_id=account_two,
            )

    @pytest.mark.asyncio
    async def test_clip_inherits_source_account_and_tags(self, db):
        """Clips are created in the source account and copy account-scoped tags."""
        account_id = await _create_account(db, "Team")
        source = await _create_service_video(db, account_id, "Source", "alpha, beta")

        with mock_ffmpeg(source_filename="Source"):
            clip = await clip_service.create_clip(
                db,
                source["id"],
                1,
                5,
                account_id=account_id,
            )

        assert clip["account_id"] == account_id
        assert clip["source_video_id"] == source["id"]
        assert await tag_service.get_video_tags(db, clip["id"], account_id=account_id) == ["alpha", "beta"]
        assert await video_service.get_video(db, clip["id"], account_id=account_id + 1) is None

    @pytest.mark.asyncio
    async def test_cut_cross_account_video_behaves_not_found(self, db):
        """Cutting another account's video raises safe not-found ValueError."""
        account_one = await _create_account(db, "Team One")
        account_two = await _create_account(db, "Team Two")
        source = await _create_service_video(db, account_one, "Source")

        with pytest.raises(ValueError, match="Video with id"):
            await clip_service.cut_video(
                db,
                source["id"],
                1,
                5,
                account_id=account_two,
            )
    @pytest.mark.asyncio
    async def test_clip_minimum_duration(self, client, db):
        """POST with duration < 1s returns 400."""
        video_id = await create_test_video(client, "Source", "")

        response = await client.post(
            f"/api/videos/{video_id}/clip",
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
            "/api/videos/999/clip",
            content=json.dumps({"start": 0, "end": 5}),
            headers={"Content-Type": "application/json"},
        )
        # Route returns 404 when source video does not exist
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clip_missing_fields(self, client, db):
        """POST without start/end fields returns 400."""
        response = await client.post(
            "/api/videos/1/clip",
            content=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_invalid_json(self, client, db):
        """POST with non-JSON body returns 400."""
        response = await client.post(
            "/api/videos/1/clip",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clip_non_numeric_times(self, client, db):
        """POST with non-numeric times returns 400."""
        response = await client.post(
            "/api/videos/1/clip",
            content=json.dumps({"start": "abc", "end": "def"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestClipPage:
    """Tests for the clip creator page."""

    @pytest.mark.asyncio
    async def test_clip_page_renders(self, client, db):
        """GET /videos/{id}/clip shows the clip creator."""
        video_id = await create_test_video(client, "Clip Source", "")

        response = await client.get(f"/videos/{video_id}/clip")
        assert response.status_code == 200
        assert "Create Clip" in response.text
        assert "clip-video" in response.text  # video element ID
        assert "clip-start" in response.text  # start range ID
        assert "clip-end" in response.text    # end range ID
        assert "create-clip-btn" in response.text  # button ID

    @pytest.mark.asyncio
    async def test_clip_page_not_found(self, client, db):
        """GET /videos/{id}/clip for missing id returns 404."""
        response = await client.get("/videos/999/clip")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_clip_page_shows_source_name(self, client, db):
        """Clip page shows the source video name."""
        video_id = await create_test_video(client, "My Awesome Video", "")

        response = await client.get(f"/videos/{video_id}/clip")
        assert "My Awesome Video" in response.text


# ── Cut endpoint tests ───────────────────────────────────────────

class TestCutValidation:
    """Tests for cut validation (no ffmpeg needed)."""

    @pytest.mark.asyncio
    async def test_cut_invalid_json(self, client, db):
        """POST with non-JSON body returns 400."""
        video_id = await create_test_video(client, "Source", "")
        response = await client.post(
            f"/api/videos/{video_id}/cut",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cut_missing_fields(self, client, db):
        """POST without start/end returns 400."""
        video_id = await create_test_video(client, "Source", "")
        response = await client.post(
            f"/api/videos/{video_id}/cut",
            content=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cut_nonexistent_video(self, client, db):
        """POST for non-existent video returns 404."""
        response = await client.post(
            "/api/videos/999/cut",
            content=json.dumps({"start": 0, "end": 5}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cut_non_numeric_times(self, client, db):
        """POST with non-numeric times returns 400."""
        video_id = await create_test_video(client, "Source", "")
        response = await client.post(
            f"/api/videos/{video_id}/cut",
            content=json.dumps({"start": "abc", "end": "def"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cut_start_after_end(self, client, db):
        """POST with start > end returns 400."""
        video_id = await create_test_video(client, "Source", "")
        response = await client.post(
            f"/api/videos/{video_id}/cut",
            content=json.dumps({"start": 30, "end": 10}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Start must be before end" in data["error"]

    @pytest.mark.asyncio
    async def test_cut_minimum_duration(self, client, db):
        """POST with duration < 1s returns 400."""
        video_id = await create_test_video(client, "Source", "")
        response = await client.post(
            f"/api/videos/{video_id}/cut",
            content=json.dumps({"start": 5, "end": 5.5}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Minimum clip duration" in data["error"]


@pytest.mark.usefixtures("db")
class TestCutWithMock:
    """Tests that mock ffmpeg/ffprobe for end-to-end cut."""

    @pytest.mark.asyncio
    async def test_cut_success(self, client, db):
        """Successful cut calls ffmpeg and redirects to video detail."""
        video_id = await create_test_video(client, "Source Vid", "alpha")

        with mock_ffmpeg(source_filename="src", has_audio=True):
            response = await client.post(
                f"/api/videos/{video_id}/cut",
                content=json.dumps({"start": 10, "end": 20}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] == video_id  # same video, modified in-place

    @pytest.mark.asyncio
    async def test_cut_ffmpeg_failure_returns_500(self, client, db):
        """When ffmpeg fails, cut endpoint returns 500."""
        video_id = await create_test_video(client, "Failing Source", "")

        # start=0, end=10 → has_after only → 3 subprocess calls now
        with mock_ffmpeg(source_filename="fail", returncode=1, has_audio=True):
            response = await client.post(
                f"/api/videos/{video_id}/cut",
                content=json.dumps({"start": 0, "end": 10}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 500
        data = response.json()
        assert "error" in data


@pytest.mark.usefixtures("db")
class TestClipCreationWithMock:
    """Tests that mock ffmpeg/ffprobe for end-to-end clip creation."""

    @pytest.mark.asyncio
    async def test_clip_creates_db_record(self, client, db):
        """Successful clip creation inserts a DB record with source_video_id."""
        video_id = await create_test_video(client, "Source Vid", "alpha, beta")

        with mock_ffmpeg(source_filename="src"):
            response = await client.post(
                f"/api/videos/{video_id}/clip",
                content=json.dumps({"start": 10, "end": 20}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        clip_id = data["id"]

        # Verify clip record in DB
        cursor = await db.execute(f"SELECT * FROM videos WHERE id = {clip_id}")
        clip = dict(await cursor.fetchone())
        assert clip["source_video_id"] == video_id
        assert clip["clip_start"] == 10.0
        assert clip["clip_end"] == 20.0
        assert clip["name"] == "Source Vid (clip)"

    @pytest.mark.asyncio
    async def test_clip_copies_source_tags(self, client, db):
        """Clip creation copies all tags from source video."""
        video_id = await create_test_video(client, "Tagged Source", "tutorial, funny, demo")

        with mock_ffmpeg(source_filename="src"):
            response = await client.post(
                f"/api/videos/{video_id}/clip",
                content=json.dumps({"start": 5, "end": 15}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 200
        data = response.json()
        clip_id = data["id"]

        # Verify clip has the same tags
        detail = await client.get(f"/videos/{clip_id}")
        assert "tutorial" in detail.text
        assert "funny" in detail.text
        assert "demo" in detail.text

    @pytest.mark.asyncio
    async def test_clip_ffmpeg_failure_returns_500(self, client, db):
        """When ffmpeg fails, clip endpoint returns 500."""
        video_id = await create_test_video(client, "Failing Source", "")

        with mock_ffmpeg(source_filename="fail", returncode=1):
            response = await client.post(
                f"/api/videos/{video_id}/clip",
                content=json.dumps({"start": 0, "end": 10}),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "ffmpeg" in data["error"].lower()
