"""
Tests for match system — stats calculator, service CRUD, and HTTP routes.

Run with: pytest tests/test_matches.py -v
"""

import pytest
from tests.conftest import create_test_video


class TestStatsCalculator:
    """Tests for pure stats computation functions (no DB needed)."""

    @pytest.mark.asyncio
    async def test_all_formulas(self):
        from app.services.stats_calculator import compute_all

        raw = {
            "minutes_played": 32.5,
            "points": 24,
            "two_point_attempts": 10,
            "two_point_made": 6,
            "three_point_attempts": 5,
            "three_point_made": 3,
            "free_throw_attempts": 4,
            "free_throw_made": 3,
            "offensive_rebounds": 2,
            "defensive_rebounds": 5,
            "total_rebounds": 7,
            "assists": 4,
            "steals": 1,
            "blocks": 0,
            "turnovers": 2,
            "personal_fouls": 3,
        }
        c = compute_all(raw)
        assert c["fg_attempts"] == 15
        assert c["fg_made"] == 9
        assert c["two_pct"] == 60.0
        assert c["three_pct"] == 60.0
        assert c["ft_pct"] == 75.0
        assert c["efg_pct"] == 70.0
        expected_ts = 24 / (30 + 1.76) * 100
        assert c["ts_pct"] == pytest.approx(expected_ts, rel=1e-3)

    @pytest.mark.asyncio
    async def test_zero_division_returns_none(self):
        from app.services.stats_calculator import compute_all

        raw = {
            "points": 0,
            "two_point_attempts": 0,
            "two_point_made": 0,
            "three_point_attempts": 0,
            "three_point_made": 0,
            "free_throw_attempts": 0,
            "free_throw_made": 0,
        }
        c = compute_all(raw)
        assert c["two_pct"] is None
        assert c["three_pct"] is None
        assert c["ft_pct"] is None
        assert c["efg_pct"] is None
        assert c["ts_pct"] is None

    @pytest.mark.asyncio
    async def test_missing_fields_default_to_zero(self):
        from app.services.stats_calculator import compute_all

        c = compute_all({})
        assert c["fg_attempts"] == 0
        assert c["fg_made"] == 0
        assert c["two_pct"] is None
        assert c["three_pct"] is None
        assert c["ft_pct"] is None
        assert c["efg_pct"] is None
        assert c["ts_pct"] is None

    @pytest.mark.asyncio
    async def test_partial_stats(self):
        from app.services.stats_calculator import compute_all

        raw = {
            "points": 10,
            "two_point_attempts": 8,
            "two_point_made": 4,
            "three_point_attempts": 0,
            "three_point_made": 0,
            "free_throw_attempts": 2,
            "free_throw_made": 2,
        }
        c = compute_all(raw)
        assert c["fg_attempts"] == 8
        assert c["two_pct"] == 50.0
        assert c["three_pct"] is None
        assert c["ft_pct"] == 100.0


class TestMatchService:
    """Tests for match_service CRUD operations (uses db fixture directly)."""

    @pytest.mark.asyncio
    async def test_create_match(self, db):
        from app.services.match_service import create_match, get_match

        match = await create_match(db, name="Test Match", match_date="2026-05-15")
        assert match["id"] >= 1
        assert match["name"] == "Test Match"
        assert match["match_date"] == "2026-05-15"
        assert match["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_match_with_optional_fields(self, db):
        from app.services.match_service import create_match

        match = await create_match(
            db,
            name="Full Match",
            match_date="2026-05-15",
            opponent="Rivals",
            location="Home Court",
            points=24,
            assists=5,
            minutes_played=32.5,
        )
        assert match["opponent"] == "Rivals"
        assert match["location"] == "Home Court"
        assert match["points"] == 24
        assert match["assists"] == 5
        assert match["minutes_played"] == 32.5

    @pytest.mark.asyncio
    async def test_create_match_missing_name_raises(self, db):
        from app.services.match_service import create_match

        with pytest.raises(ValueError, match="required"):
            await create_match(db, name="", match_date="2026-05-15")

    @pytest.mark.asyncio
    async def test_create_match_missing_date_raises(self, db):
        from app.services.match_service import create_match

        with pytest.raises(ValueError, match="required"):
            await create_match(db, name="Test", match_date="")

    @pytest.mark.asyncio
    async def test_get_match_not_found(self, db):
        from app.services.match_service import get_match

        match = await get_match(db, 9999)
        assert match is None

    @pytest.mark.asyncio
    async def test_list_matches_empty(self, db):
        from app.services.match_service import list_matches

        matches = await list_matches(db)
        assert matches == []

    @pytest.mark.asyncio
    async def test_list_matches_order_by_date_desc(self, db):
        from app.services.match_service import create_match, list_matches

        await create_match(db, name="Older", match_date="2026-05-01")
        await create_match(db, name="Newer", match_date="2026-05-15")

        matches = await list_matches(db)
        assert len(matches) == 2
        assert matches[0]["name"] == "Newer"
        assert matches[1]["name"] == "Older"

    @pytest.mark.asyncio
    async def test_update_match_name_date(self, db):
        from app.services.match_service import create_match, update_match, get_match

        match = await create_match(db, name="Original", match_date="2026-05-01")
        await update_match(db, match["id"], name="Updated", match_date="2026-05-20")
        updated = await get_match(db, match["id"])
        assert updated["name"] == "Updated"
        assert updated["match_date"] == "2026-05-20"

    @pytest.mark.asyncio
    async def test_update_match_stats(self, db):
        from app.services.match_service import create_match, update_match, get_match

        match = await create_match(db, name="Stats Update", match_date="2026-05-15")
        await update_match(db, match["id"], points=30, assists=10)
        updated = await get_match(db, match["id"])
        assert updated["points"] == 30
        assert updated["assists"] == 10
        assert updated["name"] == "Stats Update"

    @pytest.mark.asyncio
    async def test_delete_match(self, db):
        from app.services.match_service import create_match, delete_match, get_match

        match = await create_match(db, name="To Delete", match_date="2026-05-15")
        assert await get_match(db, match["id"]) is not None

        result = await delete_match(db, match["id"])
        assert result is True
        assert await get_match(db, match["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_match_not_found(self, db):
        from app.services.match_service import delete_match

        result = await delete_match(db, 9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_match_cascade_cleans_up(self, db):
        from app.services.match_service import create_match, link_video, delete_match

        match = await create_match(db, name="Cascade", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Vid", "v.mp4", "v.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM match_videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

        await delete_match(db, match["id"])

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM match_videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 0

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM videos")
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    @pytest.mark.asyncio
    async def test_link_video(self, db):
        from app.services.match_service import create_match, link_video

        match = await create_match(db, name="Link Test", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Linked", "l.mp4", "l.mp4", "video/mp4", 100),
        )
        await db.commit()

        await link_video(db, match["id"], 1)

        cursor = await db.execute(
            "SELECT * FROM match_videos WHERE match_id=? AND video_id=?",
            (match["id"], 1),
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_unlink_video(self, db):
        from app.services.match_service import create_match, link_video, unlink_video

        match = await create_match(db, name="Unlink Test", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("V1", "v1.mp4", "v1.mp4", "video/mp4", 100),
        )
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("V2", "v2.mp4", "v2.mp4", "video/mp4", 100),
        )
        await db.commit()

        await link_video(db, match["id"], 1)
        await link_video(db, match["id"], 2)

        await unlink_video(db, match["id"], 1)

        cursor = await db.execute(
            "SELECT video_id FROM match_videos WHERE match_id=?",
            (match["id"],),
        )
        rows = await cursor.fetchall()
        remaining = [r["video_id"] for r in rows]
        assert remaining == [2]

    @pytest.mark.asyncio
    async def test_get_match_with_videos(self, db):
        from app.services.match_service import create_match, link_video, get_match_with_videos

        match = await create_match(db, name="With Videos", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("My Video", "mv.mp4", "mv.mp4", "video/mp4", 200),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        result = await get_match_with_videos(db, match["id"])
        assert result is not None
        assert result["name"] == "With Videos"
        assert len(result["videos"]) == 1
        assert result["videos"][0]["name"] == "My Video"

    @pytest.mark.asyncio
    async def test_get_match_with_videos_not_found(self, db):
        from app.services.match_service import get_match_with_videos

        result = await get_match_with_videos(db, 9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_unlinked_videos(self, db):
        from app.services.match_service import create_match, link_video, get_unlinked_videos

        match = await create_match(db, name="Unlinked", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("LinkedVid", "l.mp4", "l.mp4", "video/mp4", 100),
        )
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("FreeVid", "f.mp4", "f.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, match["id"], 1)

        unlinked = await get_unlinked_videos(db, match["id"])
        assert len(unlinked) == 1
        assert unlinked[0]["name"] == "FreeVid"

    @pytest.mark.asyncio
    async def test_get_video_matches(self, db):
        from app.services.match_service import create_match, link_video, get_video_matches

        m1 = await create_match(db, name="Match A", match_date="2026-05-01")
        m2 = await create_match(db, name="Match B", match_date="2026-05-15")
        await db.execute(
            "INSERT INTO videos (name, filename, original_name, mime_type, file_size) VALUES (?, ?, ?, ?, ?)",
            ("Shared", "s.mp4", "s.mp4", "video/mp4", 100),
        )
        await db.commit()
        await link_video(db, m1["id"], 1)
        await link_video(db, m2["id"], 1)

        matches = await get_video_matches(db, 1)
        assert len(matches) == 2
        assert matches[0]["name"] == "Match B"


class TestMatchRoutes:
    """Tests for match HTTP endpoints (uses client fixture)."""

    @pytest.mark.asyncio
    async def test_home_page_returns_match_list(self, client):
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_videos_page_still_accessible(self, client):
        response = await client.get("/videos")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_match_via_route(self, client):
        response = await client.post(
            "/api/matches",
            data={"name": "Route Match", "match_date": "2026-05-15"},
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/matches/")

    @pytest.mark.asyncio
    async def test_create_match_missing_name(self, client):
        response = await client.post(
            "/api/matches",
            data={"match_date": "2026-05-15"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_match_detail_page(self, client):
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Detail Test", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 200
        assert "Detail Test" in detail.text

    @pytest.mark.asyncio
    async def test_match_detail_not_found(self, client):
        response = await client.get("/matches/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_new_match_form(self, client):
        response = await client.get("/matches/new")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edit_match_form(self, client):
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Edit Me", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        edit_page = await client.get(f"/matches/{match_id}/edit")
        assert edit_page.status_code == 200
        assert "Edit Me" in edit_page.text

    @pytest.mark.asyncio
    async def test_update_match_via_route(self, client):
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Before", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        await client.post(
            f"/api/matches/{match_id}",
            data={"name": "After Update", "match_date": "2026-05-16", "points": "30"},
        )

        detail = await client.get(f"/matches/{match_id}")
        assert "After Update" in detail.text

    @pytest.mark.asyncio
    async def test_delete_match_via_route(self, client):
        create_resp = await client.post(
            "/api/matches",
            data={"name": "Delete Me", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        delete_resp = await client.post(f"/matches/{match_id}/delete")
        assert delete_resp.status_code == 303
        assert delete_resp.headers["location"] == "/"

        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_match_not_found(self, client):
        response = await client.post("/matches/999/delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_video_round_trip(self, client):
        video_id = await create_test_video(client, "Linkable Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Video Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        link_resp = await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
        )
        assert link_resp.status_code == 200

        detail = await client.get(f"/matches/{match_id}")
        assert "Linkable Video" in detail.text

    @pytest.mark.asyncio
    async def test_unlink_video_round_trip(self, client):
        video_id = await create_test_video(client, "Removable Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Remove Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
        )

        remove_resp = await client.post(
            f"/api/matches/{match_id}/videos/{video_id}/remove",
        )
        assert remove_resp.status_code == 200

        detail = await client.get(f"/matches/{match_id}")
        # Video now appears in the unlinked picker but not in linked videos
        # Should show empty state for linked videos section
        assert "videos linked" in detail.text.lower() or "aucune vidéo" in detail.text.lower()

    @pytest.mark.asyncio
    async def test_match_detail_shows_stats(self, client):
        create_resp = await client.post(
            "/api/matches",
            data={
                "name": "Stats Display",
                "match_date": "2026-05-15",
                "points": "24",
                "two_point_attempts": "10",
                "two_point_made": "6",
                "three_point_attempts": "5",
                "three_point_made": "3",
            },
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        assert "PTS" in detail.text
        assert "24" in detail.text
        assert "FG%" in detail.text or "FG" in detail.text


class TestMatchLinkingUI:
    """Tests for video linking interactive UI (Checkpoint 3)."""

    @pytest.mark.asyncio
    async def test_link_video_htmx_fragment(self, client):
        """POST /api/matches/{id}/videos returns HTML fragment with linked videos."""
        video_id = await create_test_video(client, "HTMX Link", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "HTMX Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        response = await client.post(
            f"/api/matches/{match_id}/videos",
            data={"video_id": str(video_id)},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should be a fragment (no full page wrapper)
        assert "HTMX Link" in response.text

    @pytest.mark.asyncio
    async def test_unlink_video_htmx_fragment(self, client):
        """POST /api/matches/{id}/videos/{vid}/remove returns HTML fragment."""
        video_id = await create_test_video(client, "Unlink Me", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Unlink Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link first
        await client.post(f"/api/matches/{match_id}/videos", data={"video_id": str(video_id)})

        # Unlink via HTMX
        response = await client.post(
            f"/api/matches/{match_id}/videos/{video_id}/remove",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        # After unlinking, the video appears in the picker but not in linked videos
        # Should show empty state message (i18n: "No videos linked")
        assert "videos linked" in response.text.lower() or "aucune" in response.text.lower()

    @pytest.mark.asyncio
    async def test_match_detail_shows_unlinked_videos_in_picker(self, client):
        """Match detail page includes unlinked videos for the picker."""
        video_id = await create_test_video(client, "Picker Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Picker Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        detail = await client.get(f"/matches/{match_id}")
        assert detail.status_code == 200
        # Should show the video in the link picker
        assert "Picker Video" in detail.text

    @pytest.mark.asyncio
    async def test_video_detail_shows_match_context(self, client):
        """Video detail page shows matches the video belongs to."""
        video_id = await create_test_video(client, "Linked Video", "")

        create_resp = await client.post(
            "/api/matches",
            data={"name": "Context Match", "match_date": "2026-05-15"},
        )
        match_id = create_resp.headers["location"].split("/")[-1]

        # Link video to match
        await client.post(f"/api/matches/{match_id}/videos", data={"video_id": str(video_id)})

        # Video detail should show match context
        detail = await client.get(f"/videos/{video_id}")
        assert detail.status_code == 200
        assert "Context Match" in detail.text

    @pytest.mark.asyncio
    async def test_video_detail_back_link_goes_to_videos(self, client):
        """Video detail back link points to /videos, not /."""
        video_id = await create_test_video(client, "Back Link", "")
        detail = await client.get(f"/videos/{video_id}")
        assert 'href="/videos"' in detail.text or 'href="/videos' in detail.text
