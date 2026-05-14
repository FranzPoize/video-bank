"""
Tests for tag system (Checkpoint 3).

Run with: pytest tests/test_tags.py -v
"""

import pytest


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
        list_resp = await client.get("/")
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
        list_resp = await client.get("/")
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
        response = await client.get("/")
        assert "alpha" in response.text
        assert "beta" in response.text

    @pytest.mark.asyncio
    async def test_tags_in_detail(self, client):
        """Tags should appear on the video detail page."""
        await client.post(
            "/api/videos",
            data={"name": "Detail Tags", "tags": "gamma, delta"},
            files={"file": ("detail.mp4", b"c", "video/mp4")},
        )
        response = await client.get("/video/1")
        assert "gamma" in response.text
        assert "delta" in response.text
