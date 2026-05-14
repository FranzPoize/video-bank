"""
Pytest fixtures for all tests.

Provides:
- An in-memory SQLite database with schema applied
- An httpx.AsyncClient against the FastAPI app
- Cleanup between tests
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.database import init_db, get_db
from app.main import app as _app


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Create a fresh in-memory database for each test."""
    db_conn = await aiosqlite.connect(":memory:")
    db_conn.row_factory = aiosqlite.Row

    # Initialize schema directly on this connection
    from app.database import MIGRATIONS
    for version in range(1, 2):  # migration_version=1
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
