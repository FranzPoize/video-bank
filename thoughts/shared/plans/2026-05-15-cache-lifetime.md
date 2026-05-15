# Cache Lifetime Strategy Implementation Plan

**Goal:** Add `Cache-Control` headers to static assets and uploaded files via a middleware, with query-param cache busting in templates.

**Architecture:** A Starlette `BaseHTTPMiddleware` that inspects the URL path of each response and sets `Cache-Control` based on the first matching prefix rule. Templates add `?v=2` to CSS/JS URLs for manual cache busting when files change.

**Design:** [thoughts/shared/designs/2026-05-15-cache-lifetime-design.md](../designs/2026-05-15-cache-lifetime-design.md)

---

## Dependency Graph

```
Batch 1 (parallel): 1.1, 1.2          [foundation - no deps]
Batch 2 (parallel): 2.1, 2.2          [tests + integration - depend on batch 1]
```

---

## Batch 1: Foundation (parallel - 2 implementers)

All tasks in this batch have NO dependencies and run simultaneously.

### Task 1.1: Create `CacheControlMiddleware`

**File:** `app/middleware.py`
**Test:** `tests/test_middleware.py` (will be created in Task 2.1)
**Depends:** none

**Implementation:** A Starlette `BaseHTTPMiddleware` subclass with ordered path-prefix rules. The middleware catches exceptions gracefully—if header injection fails, the response is returned without cache headers and a WARNING is logged.

```python
"""
Cache-Control header injection middleware.

Sets Cache-Control headers on responses based on URL path patterns.
First-match-wins ordering: more specific rules come first.
"""

import logging
from typing import List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Ordered list of (path_prefix, cache_directive) rules. First match wins.
# More specific prefixes must come before broader ones.
CACHE_RULES: List[Tuple[str, str]] = [
    ("/static/js/htmx.min.js", "public, max-age=31536000, immutable"),
    ("/static/", "public, max-age=2592000, immutable"),
    ("/uploads/thumbnails/", "public, max-age=604800"),
    ("/uploads/videos/", "public, max-age=86400"),
]


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Middleware that sets Cache-Control headers based on URL path patterns.

    Inspects the URL path of every response and applies the first matching
    cache rule. Paths that don't match any rule are left unchanged.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        try:
            path = request.url.path
            for prefix, directive in CACHE_RULES:
                if path.startswith(prefix):
                    response.headers["Cache-Control"] = directive
                    break
        except Exception:
            logger.warning(
                "CacheControlMiddleware failed to set headers for path: %s",
                request.url.path,
            )
        return response
```

**Verify:** `python -c "from app.middleware import CacheControlMiddleware; print('OK')"`
**Commit:** `feat(cache): add CacheControlMiddleware with path-based rules`

---

### Task 1.2: Update template with versioned static URLs

**File:** `app/templates/base.html` (modify)
**Test:** none (template change, verified by inspection)
**Depends:** none

**Changes:**
- `href="/static/css/style.css"` → `href="/static/css/style.css?v=2"`
- `src="/static/js/upload.js"` → `src="/static/js/upload.js?v=2"`
- `src="/static/js/clipper.js"` → `src="/static/js/clipper.js?v=2"`
- `src="/static/js/htmx.min.js"` — unchanged (vendored, 1-year immutable, never changes)

**Exact edits to apply:**

Edit 1 — line 9: Add version to stylesheet link
```diff
-    <link rel="stylesheet" href="/static/css/style.css">
+    <link rel="stylesheet" href="/static/css/style.css?v=2">
```

Edit 2 — line 81: Add version to upload.js
```diff
-    <script src="/static/js/upload.js"></script>
+    <script src="/static/js/upload.js?v=2"></script>
```

Edit 3 — line 82: Add version to clipper.js
```diff
-    <script src="/static/js/clipper.js"></script>
+    <script src="/static/js/clipper.js?v=2"></script>
```

**Verify:** Inspect file manually or `grep -c 'v=2' app/templates/base.html` (should return 3 matches)
**Commit:** `feat(cache): add ?v=2 query params to static assets in base template`

---

## Batch 2: Implementation + Tests (parallel - 2 implementers)

Both tasks depend on Batch 1 completing (import from middleware.py in Task 2.1 requires the file to exist; Task 2.2 imports from middleware.py and registers it).

### Task 2.1: Write middleware tests

**File:** `tests/test_middleware.py` (new)
**Test:** This IS the test file
**Depends:** 1.1 (imports `CacheControlMiddleware` from `app.middleware`)

**Implementation notes:**
- Creates an isolated FastAPI app with only the middleware registered (doesn't depend on main.py or conftest.py)
- Uses `httpx.AsyncClient` with `ASGITransport` (same pattern as conftest.py)
- Defines module-level `app` and `client` fixtures that shadow conftest's fixtures for this test file only
- Covers: 4 cache tiers, homepage, API routes, query param invariance, rule priority

```python
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
```

**Verify:** `pytest tests/test_middleware.py -v` (all 11 tests pass)
**Commit:** `test(cache): add tests for CacheControlMiddleware`

---

### Task 2.2: Register middleware in app entry point

**File:** `app/main.py` (modify)
**Test:** none (verified by integration tests in Task 2.1)
**Depends:** 1.1 (imports `CacheControlMiddleware` from `app.middleware`)

**Changes:** Add two lines after `app = FastAPI(title="Video Bank")` (line 36):
1. Import `CacheControlMiddleware` from `app.middleware`
2. Register it via `app.add_middleware()`

**Exact edits to apply:**

Edit 1 — Add import after the existing app imports (around line 24-32):
```diff
 from app.routes.tags import router as tags_router
+from app.middleware import CacheControlMiddleware
 from app.templates import (
```

Edit 2 — Register middleware after `app = FastAPI(title="Video Bank")` (line 37):
```diff
 app = FastAPI(title="Video Bank")
+app.add_middleware(CacheControlMiddleware)

 # Mount static directories for uploaded files
```

**Verify:** `python -c "from app.main import app; print(app.user_middleware[-1].cls.__name__)"` should print `CacheControlMiddleware`
**Commit:** `feat(cache): register CacheControlMiddleware in main app`

---

## Verification

After all tasks complete, run the full test suite:

```bash
pytest tests/ -v
```

All 11 new middleware tests plus all existing tests must pass.

---

## Commit Order

1. `feat(cache): add CacheControlMiddleware with path-based rules` (Task 1.1)
2. `feat(cache): add ?v=2 query params to static assets in base template` (Task 1.2)
3. `test(cache): add tests for CacheControlMiddleware` (Task 2.1)
4. `feat(cache): register CacheControlMiddleware in main app` (Task 2.2)
