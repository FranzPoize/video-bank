"""
Pytest fixtures for all tests.

Provides:
- An in-memory SQLite database with schema applied
- An httpx.AsyncClient against the FastAPI app
- Cleanup between tests
"""

import asyncio
import os
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


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Create a fresh in-memory database for each test."""
    db_conn = await aiosqlite.connect(":memory:")
    await db_conn.execute("PRAGMA foreign_keys = ON")
    db_conn.row_factory = aiosqlite.Row

    # Initialize schema directly on this connection
    from app.database import MIGRATIONS
    for version in range(1, 6):  # migration_version=5 (includes match schema)
        for stmt in MIGRATIONS.get(version, []):
            await db_conn.execute(stmt)
    await db_conn.commit()

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

        # Mock ffprobe subprocess (duration)
        mock_ffprobe_proc = AsyncMock()
        mock_ffprobe_proc.returncode = 0
        mock_ffprobe_proc.communicate = AsyncMock(
            return_value=(f"{duration}\n".encode(), b"")
        )

        # Mock ffmpeg subprocess
        mock_ffmpeg_proc = AsyncMock()
        mock_ffmpeg_proc.returncode = returncode
        mock_ffmpeg_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error output" if returncode != 0 else b""))

        # Build side_effect list — cut_video also calls _has_audio_stream
        if has_audio:
            mock_ffprobe_audio = AsyncMock()
            mock_ffprobe_audio.returncode = 0
            mock_ffprobe_audio.communicate = AsyncMock(
                return_value=(b"audio\n", b"")
            )
            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffprobe_audio, mock_ffmpeg_proc]
        else:
            mock_subproc.side_effect = [mock_ffprobe_proc, mock_ffmpeg_proc]

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
