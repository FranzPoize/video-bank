"""
Tests for CacheControlMiddleware cache header injection.

Run with: pytest tests/test_middleware.py -v

Covers:
- Cache-Control header correctness for each cache tier
- Query parameter invariance (?v=N doesn't affect caching)
- Non-static routes (API, HTML pages) not affected
- First-match-wins priority ordering
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from app.middleware import CacheControlMiddleware


@pytest.fixture
def app():
    """Minimal FastAPI app with CacheControlMiddleware and a catch-all route.

    Uses an isolated app so tests don't depend on the real application
    setup (database, routes, static mounts, etc.).
    """
    application = FastAPI()
    application.add_middleware(CacheControlMiddleware)

    @application.api_route("/{path:path}", methods=["GET", "HEAD"])
    async def catch_all() -> Response:
        return Response(content="ok", media_type="text/plain")

    return application


@pytest.fixture
async def client(app):
    """Async HTTP client against the minimal test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCacheTiers:
    """Verify correct Cache-Control headers for each cache tier."""

    @pytest.mark.asyncio
    async def test_htmx_min_js_one_year_immutable(self, client):
        """htmx.min.js gets 1-year cache with immutable directive."""
        response = await client.get("/static/js/htmx.min.js")
        cc = response.headers.get("cache-control", "")
        assert "max-age=31536000" in cc
        assert "immutable" in cc

    @pytest.mark.asyncio
    async def test_static_css_thirty_days_immutable(self, client):
        """CSS files under /static/ get 30-day cache with immutable."""
        response = await client.get("/static/css/style.css")
        cc = response.headers.get("cache-control", "")
        assert "max-age=2592000" in cc
        assert "immutable" in cc

    @pytest.mark.asyncio
    async def test_static_js_thirty_days_immutable(self, client):
        """JS files (upload.js) under /static/ get 30-day cache."""
        response = await client.get("/static/js/upload.js")
        cc = response.headers.get("cache-control", "")
        assert "max-age=2592000" in cc
        assert "immutable" in cc

    @pytest.mark.asyncio
    async def test_thumbnails_seven_days_public(self, client):
        """Thumbnails under /uploads/thumbnails/ get 7-day public cache."""
        response = await client.get("/uploads/thumbnails/video1.webp")
        cc = response.headers.get("cache-control", "")
        assert "max-age=604800" in cc
        assert "public" in cc

    @pytest.mark.asyncio
    async def test_videos_one_day_public(self, client):
        """Video files under /uploads/videos/ get 1-day public cache."""
        response = await client.get("/uploads/videos/movie.mp4")
        cc = response.headers.get("cache-control", "")
        assert "max-age=86400" in cc
        assert "public" in cc


class TestNonCachedRoutes:
    """Routes not matching any cache rule should have no Cache-Control header."""

    @pytest.mark.asyncio
    async def test_homepage_no_cache_header(self, client):
        """HTML pages should not get Cache-Control headers."""
        response = await client.get("/")
        assert "cache-control" not in response.headers

    @pytest.mark.asyncio
    async def test_api_route_no_cache_header(self, client):
        """API routes should not get Cache-Control headers."""
        response = await client.get("/api/videos")
        assert "cache-control" not in response.headers

    @pytest.mark.asyncio
    async def test_unknown_path_no_cache_header(self, client):
        """Unknown/unmatched paths should not get Cache-Control headers."""
        response = await client.get("/some/random/path")
        assert "cache-control" not in response.headers


class TestCacheBusting:
    """Query parameters (?v=N) should not affect cache header behavior."""

    @pytest.mark.asyncio
    async def test_query_params_ignored_for_cache_headers(self, client):
        """Same path with and without query params gets same Cache-Control."""
        resp1 = await client.get("/static/css/style.css")
        resp2 = await client.get("/static/css/style.css?v=2")
        assert resp1.headers.get("cache-control") == resp2.headers.get("cache-control")

    @pytest.mark.asyncio
    async def test_different_version_numbers_produce_same_header(self, client):
        """Different ?v= values produce identical Cache-Control headers."""
        resp1 = await client.get("/static/css/style.css?v=1")
        resp2 = await client.get("/static/css/style.css?v=99")
        assert resp1.headers.get("cache-control") == resp2.headers.get("cache-control")


class TestRulePriority:
    """First-match-wins ordering: specific rules before generic rules."""

    @pytest.mark.asyncio
    async def test_htmx_rule_takes_priority_over_generic_static(self, client):
        """htmx.min.js matches specific rule (1 year), not generic /static/ (30 days)."""
        response = await client.get("/static/js/htmx.min.js")
        cc = response.headers.get("cache-control", "")
        assert "max-age=31536000" in cc  # 1 year (specific htmx rule)
        assert "max-age=2592000" not in cc  # NOT 30 days (generic static rule)
