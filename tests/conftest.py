"""
Pytest fixtures for all tests.

Provides:
- An in-memory SQLite database with schema applied
- An httpx.AsyncClient against the FastAPI app
- Cleanup between tests
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import init_db, get_db
from app.main import app as _app
from app.dependencies import AUTH_SESSION_COOKIE
from app.services import account_service, security_service, session_service


def pytest_configure(config):
    config.addinivalue_line("markers", "no_auto_auth: disable checkpoint route auto-auth fixture")


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Create a fresh in-memory database for each test."""
    db_conn = await aiosqlite.connect(":memory:")
    await db_conn.execute("PRAGMA foreign_keys = ON")
    db_conn.row_factory = aiosqlite.Row

    # Initialize schema directly on this connection
    from app.database import MIGRATIONS
    for version in range(1, 8):  # migration_version=7 (includes account-scoped content)
        for stmt in MIGRATIONS.get(version, []):
            if isinstance(stmt, str):
                await db_conn.execute(stmt)
            else:
                await stmt(db_conn)
    await db_conn.commit()
    await db_conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield db_conn
    finally:
        await db_conn.close()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx test client against the FastAPI app with DB override."""
    _app.dependency_overrides[get_db] = lambda: db

    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    _app.dependency_overrides.clear()


@contextmanager
def mock_ffmpeg(source_filename="src.mp4", duration=60.0, returncode=0, has_audio=False):
    """Context manager that mocks ffmpeg/ffprobe for clip tests.

    Sets up:
    - shutil.which returning paths for ffprobe and ffmpeg
    - create_subprocess_exec returning mocked processes
    - file_service.get_video_path returning appropriate paths
    - file_service.generate_thumbnail as a no-op

    Args:
        source_filename: The filename that triggers "source" path matching.
        duration: Duration in seconds that ffprobe returns.
        returncode: Return code for the ffmpeg subprocess (0 = success).
        has_audio: When True, adds an extra ffprobe mock for
                   ``_has_audio_stream`` (needed by cut_video).

    Yields:
        Tuple of (mock_which, mock_subproc) for additional assertions.
    """
    with patch("app.services.clip_service.shutil.which") as mock_which, \
         patch("app.services.clip_service.asyncio.create_subprocess_exec") as mock_subproc:

        mock_which.side_effect = lambda cmd: {
            "ffprobe": "/usr/bin/ffprobe",
            "ffmpeg": "/usr/bin/ffmpeg",
        }.get(cmd)

        def _subproc_side_effect(*args, **kwargs):
            """Return the appropriate mock process for any subprocess call."""
            binary = args[0]
            proc = AsyncMock()
            if "ffprobe" in binary:
                proc.returncode = 0
                out = f"{duration}\n".encode()
                # Handle _has_audio_stream if called
                if "-select_streams" in args:
                    out = b"audio\n" if has_audio else b""
                proc.communicate = AsyncMock(return_value=(out, b""))
            else:
                proc.returncode = returncode
                proc.communicate = AsyncMock(
                    return_value=(b"", b"ffmpeg error output" if returncode != 0 else b"")
                )
            return proc

        mock_subproc.side_effect = _subproc_side_effect

        # Mock file paths
        with patch("app.services.clip_service.file_service.get_video_path") as mock_get_path, \
             patch("app.services.clip_service.file_service.generate_thumbnail", AsyncMock(return_value=True)):

            def _make_stat(size=1024):
                return type("Stat", (), {"st_size": size})()

            def _make_path(exists=True):
                stats = {"st_size": 1024}

                class MockPath:
                    def exists(self):
                        return exists

                    def stat(self):
                        return type("Stat", (), stats)()

                    def unlink(self):
                        pass

                    def with_name(self, name):
                        return _make_path(exists)

                    def replace(self, dest):
                        pass

                return MockPath()

            mock_src_path = _make_path(True)
            mock_clip_path = _make_path(returncode == 0)

            def get_path_side_effect(filename):
                if source_filename in filename:
                    return mock_src_path
                return mock_clip_path

            mock_get_path.side_effect = get_path_side_effect

            yield (mock_which, mock_subproc)


async def create_test_video(client, name: str, tags: str = "") -> int:
    """Upload a test video and return its numeric ID.

    Uses X-Requested-With header to get JSON response with the ID.
    """
    response = await client.post(
        "/api/videos",
        data={"name": name, "tags": tags},
        files={"file": (f"{name}.mp4", b"fake-video-content", "video/mp4")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    return response.json()["id"]


async def create_test_user_with_account(
    db,
    email: str = "user@example.com",
    password: str = "password",
    account_name: str = "Test Account",
    capabilities: dict | None = None,
) -> dict:
    """Create a verified user, account membership, and active session token for route tests."""
    cursor = await db.execute(
        """
        INSERT INTO users (email, normalized_email, password_hash, is_email_verified)
        VALUES (?, ?, ?, 1)
        """,
        (email, email.strip().lower(), security_service.hash_password(password)),
    )
    await db.commit()
    user_id = cursor.lastrowid

    created = await account_service.create_account_with_admin_membership(db, user_id, account_name)
    if capabilities is not None:
        values = {
            "manage_videos": 0,
            "manage_matches": 0,
            "manage_tags": 0,
            "manage_account_settings": 0,
            "manage_members": 0,
            "admin": 0,
        }
        values.update({key: 1 if value else 0 for key, value in capabilities.items()})
        await db.execute(
            """
            UPDATE account_memberships
            SET manage_videos = ?, manage_matches = ?, manage_tags = ?,
                manage_account_settings = ?, manage_members = ?, admin = ?
            WHERE id = ?
            """,
            (
                values["manage_videos"],
                values["manage_matches"],
                values["manage_tags"],
                values["manage_account_settings"],
                values["manage_members"],
                values["admin"],
                created["membership"]["id"],
            ),
        )
        await db.commit()
        created["membership"] = await account_service.get_membership(db, user_id, created["account"]["id"])

    session = await session_service.create_session(
        db,
        user_id=user_id,
        active_account_id=created["account"]["id"],
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    return {"user_id": user_id, "account": created["account"], "membership": created["membership"], "session": session}


async def login_test_user(client, db, **kwargs) -> dict:
    """Create and attach an authenticated test user cookie to the client."""
    context = await create_test_user_with_account(db, **kwargs)
    client.cookies.set(AUTH_SESSION_COOKIE, context["session"]["token"], domain="test.local")
    client.cookies.set(AUTH_SESSION_COOKIE, context["session"]["token"])
    return context


@pytest_asyncio.fixture
async def auth_context(client, db):
    """Authenticated admin user context for route tests."""
    return await login_test_user(client, db)


@pytest_asyncio.fixture(autouse=True)
async def auto_auth_checkpoint3_route_tests(request, client, db):
    """Keep legacy route tests authenticated while explicit anonymous tests opt out."""
    if request.node.get_closest_marker("no_auto_auth"):
        return
    module_path = str(getattr(request.node, "path", ""))
    if module_path.endswith(("test_videos.py", "test_tags.py", "test_matches.py", "test_clips.py")):
        await login_test_user(client, db, email=f"{request.node.name}@example.com")
