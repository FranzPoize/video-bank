"""Checkpoint 6 account isolation regression tests.

These tests exercise HTTP routes across two authenticated accounts to ensure
account-scoped videos, matches, tags, media files, and settings never leak via
reads or writes.
"""

from pathlib import Path

import pytest

from app.dependencies import AUTH_SESSION_COOKIE
from app.services.file_service import THUMBNAILS_DIR, THUMBNAIL_EXT
from tests.conftest import create_test_video, login_test_user


async def _create_match(client, name: str = "Match") -> int:
    response = await client.post(
        "/api/matches",
        data={"name": name, "match_date": "2026-05-20"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[1])


async def _video_filename(db, video_id: int) -> str:
    cursor = await db.execute("SELECT filename FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    assert row is not None
    return row["filename"]


@pytest.mark.asyncio
async def test_cross_account_video_reads_streams_thumbnails_and_writes_are_blocked(client, db):
    """Another account cannot see, stream, thumbnail, edit, tag, or delete a video."""
    await login_test_user(client, db, email="video-owner@example.com")
    video_id = await create_test_video(client, "Owner Private Video", "owner-only")
    filename = await _video_filename(db, video_id)
    thumb_path = THUMBNAILS_DIR / f"{Path(filename).stem}.{THUMBNAIL_EXT}"
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.write_bytes(b"owner-thumbnail")

    try:
        assert (await client.get(f"/videos/{video_id}")).status_code == 200
        assert (await client.get(f"/api/videos/{video_id}/file")).status_code == 200
        assert (await client.get(f"/api/videos/{video_id}/thumbnail")).content == b"owner-thumbnail"

        client.cookies.clear()
        await login_test_user(client, db, email="video-intruder@example.com")

        assert (await client.get(f"/videos/{video_id}")).status_code == 404
        assert (await client.get(f"/videos/{video_id}/edit")).status_code == 404
        assert (await client.get(f"/videos/{video_id}/clip")).status_code == 404
        assert (await client.get(f"/api/videos/{video_id}/file")).status_code == 404
        assert (await client.get(f"/api/videos/{video_id}/thumbnail")).status_code == 404

        edit = await client.post(
            f"/videos/{video_id}/edit",
            data={"name": "Leaked Name", "tags": "leaked-tag"},
            follow_redirects=False,
        )
        delete = await client.post(f"/videos/{video_id}/delete", follow_redirects=False)
        clip = await client.post(f"/api/videos/{video_id}/clip", json={"start": 0, "end": 1})
        cut = await client.post(f"/api/videos/{video_id}/cut", json={"start": 0, "end": 1})

        assert edit.status_code == 404
        assert delete.status_code == 404
        assert clip.status_code == 404
        assert cut.status_code == 404

        client.cookies.clear()
        await login_test_user(client, db, email="video-owner-return@example.com")
        # New account with same user email pattern still must not see owner's resource.
        assert (await client.get(f"/videos/{video_id}")).status_code == 404

        cursor = await db.execute("SELECT name FROM videos WHERE id = ?", (video_id,))
        row = await cursor.fetchone()
        assert row["name"] == "Owner Private Video"
    finally:
        if thumb_path.exists():
            thumb_path.unlink()


@pytest.mark.asyncio
async def test_cross_account_match_reads_writes_and_video_links_are_blocked(client, db):
    """Match routes must not reveal or mutate another account or cross-link videos."""
    await login_test_user(client, db, email="match-owner@example.com")
    owner_video_id = await create_test_video(client, "Owner Video", "")
    owner_match_id = await _create_match(client, "Owner Match")

    client.cookies.clear()
    await login_test_user(client, db, email="match-other@example.com")
    other_video_id = await create_test_video(client, "Other Video", "")
    other_match_id = await _create_match(client, "Other Match")

    assert (await client.get(f"/matches/{owner_match_id}")).status_code == 404
    assert (await client.get(f"/matches/{owner_match_id}/edit")).status_code == 404
    assert (
        await client.get(f"/api/matches/{owner_match_id}/videos/{owner_video_id}/player")
    ).status_code == 404

    update = await client.post(
        f"/api/matches/{owner_match_id}",
        data={"name": "Leaked Match", "match_date": "2026-05-21"},
    )
    delete = await client.post(f"/matches/{owner_match_id}/delete", follow_redirects=False)
    link_to_owner_match = await client.post(
        f"/api/matches/{owner_match_id}/videos",
        data={"video_id": str(other_video_id)},
    )
    link_owner_video = await client.post(
        f"/api/matches/{other_match_id}/videos",
        data={"video_id": str(owner_video_id)},
    )
    unlink_owner_video = await client.post(
        f"/api/matches/{owner_match_id}/videos/{owner_video_id}/remove",
    )

    assert update.status_code == 404
    assert delete.status_code == 404
    assert link_to_owner_match.status_code == 404
    assert link_owner_video.status_code == 404
    assert unlink_owner_video.status_code == 404

    cursor = await db.execute("SELECT name FROM matches WHERE id = ?", (owner_match_id,))
    row = await cursor.fetchone()
    assert row["name"] == "Owner Match"
    cursor = await db.execute("SELECT COUNT(*) AS cnt FROM match_videos")
    row = await cursor.fetchone()
    assert row["cnt"] == 0


@pytest.mark.asyncio
async def test_cross_account_video_remove_from_owned_match_is_404(client, db):
    """Removing a foreign-account video from an owned match must not succeed."""
    owner_context = await login_test_user(client, db, email="remove-owner@example.com")
    own_match_id = await _create_match(client, "Remove Owner Match")

    client.cookies.clear()
    await login_test_user(client, db, email="remove-foreign@example.com")
    foreign_video_id = await create_test_video(client, "Foreign Remove Video", "")

    client.cookies.clear()
    client.cookies.set(AUTH_SESSION_COOKIE, owner_context["session"]["token"], domain="test.local")
    client.cookies.set(AUTH_SESSION_COOKIE, owner_context["session"]["token"])
    response = await client.post(
        f"/api/matches/{own_match_id}/videos/{foreign_video_id}/remove",
    )

    assert response.status_code == 404

    cursor = await db.execute("SELECT COUNT(*) AS cnt FROM match_videos")
    row = await cursor.fetchone()
    assert row["cnt"] == 0


@pytest.mark.asyncio
async def test_cross_account_tag_reads_writes_and_settings_are_scoped(client, db):
    """Tag APIs and settings page only expose and mutate active-account tags."""
    await login_test_user(client, db, email="tag-owner@example.com")
    await create_test_video(client, "Owner Tagged", "owner-secret")
    owner_tag = await (await db.execute("SELECT id FROM tags WHERE name = 'owner-secret'")).fetchone()
    assert owner_tag is not None

    owner_settings = await client.get("/settings")
    assert owner_settings.status_code == 200
    assert "owner-secret" in owner_settings.text

    client.cookies.clear()
    await login_test_user(client, db, email="tag-other@example.com")
    await create_test_video(client, "Other Tagged", "other-secret")
    other_tag = await (await db.execute("SELECT id FROM tags WHERE name = 'other-secret'")).fetchone()
    assert other_tag is not None

    settings = await client.get("/settings")
    tags = await client.get("/api/tags")

    assert settings.status_code == 200
    assert "other-secret" in settings.text
    assert "owner-secret" not in settings.text
    assert tags.status_code == 200
    assert tags.json()["tags"] == ["other-secret"]

    rename_owner = await client.post(
        f"/api/tags/{owner_tag['id']}/rename",
        data={"new_name": "leaked-owner-tag"},
        follow_redirects=False,
    )
    delete_owner = await client.post(
        f"/api/tags/{owner_tag['id']}/delete",
        follow_redirects=False,
    )
    rename_other = await client.post(
        f"/api/tags/{other_tag['id']}/rename",
        data={"new_name": "other-renamed"},
        follow_redirects=False,
    )

    assert rename_owner.status_code == 404
    assert delete_owner.status_code == 404
    assert rename_other.status_code == 303

    cursor = await db.execute("SELECT name FROM tags WHERE id = ?", (owner_tag["id"],))
    row = await cursor.fetchone()
    assert row["name"] == "owner-secret"

    settings_after = await client.get("/settings")
    assert "other-renamed" in settings_after.text
    assert "owner-secret" not in settings_after.text
