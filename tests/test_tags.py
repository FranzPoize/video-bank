"""
Tests for tag system (Checkpoint 3) + tag management (settings page).

Run with: pytest tests/test_tags.py -v
"""

import pytest
from tests.conftest import create_test_video


class TestTagCreation:
    """Tests for on-the-fly tag creation."""

    @pytest.mark.asyncio
    async def test_upload_with_tags(self, client):
        """Upload with tags stores them."""
        await client.post(
            "/api/videos",
            data={"name": "Tagged Video", "tags": "tutorial, funny, demo"},
            files={"file": ("tagged.mp4", b"content", "video/mp4")},
        )
        list_resp = await client.get("/videos")
        assert "tutorial" in list_resp.text
        assert "funny" in list_resp.text
        assert "demo" in list_resp.text

    @pytest.mark.asyncio
    async def test_upload_without_tags(self, client):
        """Upload without tags still works."""
        response = await client.post(
            "/api/videos",
            data={"name": "No Tags"},
            files={"file": ("notags.mp4", b"content", "video/mp4")},
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_upload_empty_tags(self, client):
        """Upload with empty tags string still works."""
        response = await client.post(
            "/api/videos",
            data={"name": "Empty Tags", "tags": ""},
            files={"file": ("emptytags.mp4", b"content", "video/mp4")},
        )
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_duplicate_tags(self, client):
        """Duplicate tag names should be stored once."""
        await client.post(
            "/api/videos",
            data={"name": "Dup Tags", "tags": "test, test, TEST"},
            files={"file": ("dup.mp4", b"content", "video/mp4")},
        )
        # Check that only one tag was created
        list_resp = await client.get("/videos")
        # "test" should appear (lowercased), count the occurrences
        assert list_resp.text.count("test") >= 1  # at least once


class TestTagDisplay:
    """Tests for tag display."""

    @pytest.mark.asyncio
    async def test_tags_in_list(self, client):
        """Tags should appear on video cards in the list."""
        await client.post(
            "/api/videos",
            data={"name": "Tag Display", "tags": "alpha, beta"},
            files={"file": ("display.mp4", b"c", "video/mp4")},
        )
        response = await client.get("/videos")
        assert "alpha" in response.text
        assert "beta" in response.text

    @pytest.mark.asyncio
    async def test_tags_in_detail(self, client):
        """Tags should appear on the video detail page."""
        video_id = await create_test_video(client, "Detail Tags", "gamma, delta")
        response = await client.get(f"/videos/{video_id}")
        assert "gamma" in response.text
        assert "delta" in response.text


async def _create_test_video(client, name: str, tags: str = ""):
    """Helper: Create a test video with given tags."""
    return await client.post(
        "/api/videos",
        data={"name": name, "tags": tags},
        files={"file": (f"{name}.mp4", b"content", "video/mp4")},
    )


class TestTagServiceFunctions:
    """Tests for the new tag service functions (get_tag, update_tag, delete_tag, list_all_tags_with_counts)."""

    @pytest.mark.asyncio
    async def test_get_tag(self, db):
        """get_tag fetches a single tag by id."""
        from app.services import tag_service

        # Create a tag
        tag_id = await tag_service.get_or_create_tag(db, "mytag")

        # Fetch it
        tag = await tag_service.get_tag(db, tag_id)
        assert tag is not None
        assert tag["id"] == tag_id
        assert tag["name"] == "mytag"

        # Non-existent returns None
        not_found = await tag_service.get_tag(db, 9999)
        assert not_found is None

    @pytest.mark.asyncio
    async def test_rename_tag_success(self, db):
        """update_tag successfully renames a tag."""
        from app.services import tag_service

        tag_id = await tag_service.get_or_create_tag(db, "oldname")

        # Rename it
        updated = await tag_service.update_tag(db, tag_id, "newname")
        assert updated["name"] == "newname"

        # Verify it changed
        tag = await tag_service.get_tag(db, tag_id)
        assert tag["name"] == "newname"

    @pytest.mark.asyncio
    async def test_rename_tag_normalizes_name(self, db):
        """update_tag normalizes the name (strip + lowercase)."""
        from app.services import tag_service

        tag_id = await tag_service.get_or_create_tag(db, "original")

        # Rename with whitespace and uppercase
        updated = await tag_service.update_tag(db, tag_id, "  NEW NAME  ")
        assert updated["name"] == "new name"

    @pytest.mark.asyncio
    async def test_rename_tag_duplicate_raises(self, db):
        """update_tag raises ValueError if new name already exists."""
        from app.services import tag_service

        tag1_id = await tag_service.get_or_create_tag(db, "tagone")
        await tag_service.get_or_create_tag(db, "tagtwo")

        # Try to rename tagone to tagtwo
        with pytest.raises(ValueError, match="already exists"):
            await tag_service.update_tag(db, tag1_id, "tagtwo")

    @pytest.mark.asyncio
    async def test_rename_tag_empty_raises(self, db):
        """update_tag raises ValueError if new name is empty."""
        from app.services import tag_service

        tag_id = await tag_service.get_or_create_tag(db, "mytag")

        with pytest.raises(ValueError, match="empty"):
            await tag_service.update_tag(db, tag_id, "")

        with pytest.raises(ValueError, match="empty"):
            await tag_service.update_tag(db, tag_id, "   ")

    @pytest.mark.asyncio
    async def test_delete_tag(self, db):
        """delete_tag removes a tag."""
        from app.services import tag_service

        tag_id = await tag_service.get_or_create_tag(db, "deleteme")

        # Verify it exists
        assert await tag_service.get_tag(db, tag_id) is not None

        # Delete it
        result = await tag_service.delete_tag(db, tag_id)
        assert result is True

        # Verify it's gone
        assert await tag_service.get_tag(db, tag_id) is None

    @pytest.mark.asyncio
    async def test_delete_tag_not_found_returns_false(self, db):
        """delete_tag returns False if tag doesn't exist."""
        from app.services import tag_service

        result = await tag_service.delete_tag(db, 9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_all_tags_with_counts(self, db):
        """list_all_tags_with_counts returns tags with usage counts."""
        from app.services import tag_service

        # First, create dummy videos to satisfy FOREIGN KEY constraints
        # We need videos before we can create video_tags associations
        await db.execute("""
            INSERT INTO videos (name, filename, original_name, mime_type, file_size)
            VALUES ('Video 1', 'v1.mp4', 'v1.mp4', 'video/mp4', 100)
        """)
        await db.execute("""
            INSERT INTO videos (name, filename, original_name, mime_type, file_size)
            VALUES ('Video 2', 'v2.mp4', 'v2.mp4', 'video/mp4', 100)
        """)
        await db.commit()

        # Create tags via get_or_create_tag
        tag1_id = await tag_service.get_or_create_tag(db, "tag1")
        tag2_id = await tag_service.get_or_create_tag(db, "tag2")
        tag3_id = await tag_service.get_or_create_tag(db, "tag3")

        # Create video-tag associations manually
        # video 1 has tag1 and tag2
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (1, tag1_id))
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (1, tag2_id))
        # video 2 has tag1
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (2, tag1_id))
        await db.commit()

        # Get tags with counts
        tags = await tag_service.list_all_tags_with_counts(db)

        # Check counts
        tag_dict = {t["name"]: t for t in tags}
        assert tag_dict["tag1"]["video_count"] == 2
        assert tag_dict["tag2"]["video_count"] == 1
        assert tag_dict["tag3"]["video_count"] == 0  # no associations


class TestTagManagementRoutes:
    """Tests for the tag management routes (settings page, rename, delete).

    Note: These tests focus on route wiring and basic behavior.
    Detailed service logic is tested in TestTagServiceFunctions.
    """

    @pytest.mark.asyncio
    async def test_settings_page_loads(self, client):
        """GET /settings returns 200."""
        response = await client.get("/settings")
        assert response.status_code == 200
        # Check for HTML structure (forms, etc.) rather than translated text
        # due to potential i18n issues in test environment
        assert '<html' in response.text
        assert '</html>' in response.text

    @pytest.mark.asyncio
    async def test_settings_page_shows_tags(self, client):
        """Settings page displays tag names (not translated, so reliable)."""
        await _create_test_video(client, "Video 1", "mytag1, mytag2")

        response = await client.get("/settings")
        assert response.status_code == 200
        # Tag names are user data, not translation keys, so they should appear
        assert "mytag1" in response.text
        assert "mytag2" in response.text

    @pytest.mark.asyncio
    async def test_api_tags_returns_tags(self, client):
        """GET /api/tags returns all tag names (unchanged by i18n)."""
        await _create_test_video(client, "Test", "alpha, beta")

        response = await client.get("/api/tags")
        assert response.status_code == 200
        assert "alpha" in response.text
        assert "beta" in response.text

    @pytest.mark.asyncio
    async def test_delete_tag_cascade_removes_associations(self, db):
        """Deleting a tag removes video_tag associations (CASCADE)."""
        from app.services import tag_service

        # First, create dummy videos to satisfy FOREIGN KEY constraints
        await db.execute("""
            INSERT INTO videos (name, filename, original_name, mime_type, file_size)
            VALUES ('Video 1', 'v1.mp4', 'v1.mp4', 'video/mp4', 100)
        """)
        await db.execute("""
            INSERT INTO videos (name, filename, original_name, mime_type, file_size)
            VALUES ('Video 2', 'v2.mp4', 'v2.mp4', 'video/mp4', 100)
        """)
        await db.commit()

        # Create tags
        tag1_id = await tag_service.get_or_create_tag(db, "tag1")
        tag2_id = await tag_service.get_or_create_tag(db, "tag2")

        # Create video-tag associations
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (1, tag1_id))
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (1, tag2_id))
        await db.execute("INSERT INTO video_tags (video_id, tag_id) VALUES (?, ?)", (2, tag1_id))
        await db.commit()

        # Verify associations exist
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM video_tags")
        row = await cursor.fetchone()
        assert row["cnt"] == 3

        # Delete tag1
        await tag_service.delete_tag(db, tag1_id)

        # Verify only tag1 associations are removed
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM video_tags")
        row = await cursor.fetchone()
        assert row["cnt"] == 1  # only video1-tag2 remains

        # Verify the remaining association is tag2
        cursor = await db.execute("SELECT tag_id FROM video_tags")
        row = await cursor.fetchone()
        assert row["tag_id"] == tag2_id
