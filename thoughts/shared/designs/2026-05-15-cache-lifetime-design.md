---
date: 2026-05-15
topic: "Cache Lifetime Strategy"
status: validated
---

## Problem Statement

Lighthouse audits flag that **all static assets have zero caching headers**. Every page load re-downloads CSS, JS, thumbnails, and video files — even though most are effectively immutable.

**Current state:** FastAPI's `StaticFiles` mount serves everything with no `Cache-Control`, `ETag`, or `Expires` headers. No reverse proxy, no CDN, no service worker.

**Assets affected:**

| Path | Size | Change Frequency |
|------|------|-----------------|
| `/static/js/htmx.min.js` | 50 KB | Never (vendored) |
| `/static/css/style.css` | 5 KB | Occasionally |
| `/static/js/upload.js` | 8 KB | Occasionally |
| `/static/js/clipper.js` | 6 KB | Occasionally |
| `/uploads/thumbnails/*.webp` | varies | Once per video |
| `/uploads/videos/*` | varies | Once (immutable) |

## Constraints

- **No build step exists** and we're not adding one. CSS/JS is served directly from source.
- **No reverse proxy** (nginx/Apache) — uvicorn serves everything directly.
- **No new dependencies** beyond what FastAPI/Starlette already provides.
- **Must not break** the HTMX-driven partial page rendering or video streaming routes.

## Approach

**Middleware-based `Cache-Control` header injection with query-param versioning.**

One Starlette middleware inspects the URL path and sets the appropriate `Cache-Control` header on the response. Templates add `?v=N` query parameters to static asset URLs for manual cache busting.

**Why this approach:**
- **Middleware is minimal** — ~30 lines, zero new dependencies, no config files
- **Query-param versioning** — handles cache busting without a build pipeline. When a file changes, bump `?v=2` to `?v=3` in the template.
- **Per-asset strategy** — treats vendored libraries differently than custom code or user uploads

**Rejected alternatives:**
- **Content-hashing build step** — Overkill. Would require adding Webpack/esbuild just for cache headers. YAGNI.
- **nginx/reverse proxy** — Adds deployment complexity. The app runs directly on uvicorn.
- **Service Worker** — Too heavy for a server-rendered HTMX app with minimal JS.

## Architecture

### Cache Tiers

```
Request → Starlette → CacheControlMiddleware → Route Handler
                       │
                       ├── htmx.min.js        → 1 year, immutable
                       ├── custom JS/CSS      → 30 days, immutable
                       ├── thumbnails         → 7 days, public
                       ├── video files        → 1 day, public
                       └── everything else    → no-cache
```

| Asset | `max-age` | Reasoning |
|-------|-----------|-----------|
| `htmx.min.js` | **31536000** (1 year) + `immutable` | Vendored library, never changes unless manually replaced. `immutable` tells browsers "don't even revalidate." |
| Custom JS (`upload.js`, `clipper.js`) and `style.css` | **2592000** (30 days) + `immutable` | Changes occasionally via code changes. Safe with `?v=N` busting. |
| Thumbnails (`*.webp`) | **604800** (7 days) + `public` | Generated once per video. 7 days balances freshness vs caching. `public` allows proxy/CDN caching if added later. |
| Video files (`*.mp4`, `*.webm`, `*.mov`) | **86400** (1 day) + `public` | Large files (up to 2GB). 1 day prevents re-download on same-day visits without serving stale content. |
| HTML pages, API routes | `no-cache` (default) | Dynamic content with search, pagination, user state. Never cache. |

### Cache Busting

When a static file changes, bump the version number in `base.html`:

```html
<link rel="stylesheet" href="/static/css/style.css?v=2">
<script src="/static/js/upload.js?v=2"></script>
<script src="/static/js/clipper.js?v=2"></script>
```

The middleware ignores query parameters — it only inspects the URL **path** to determine the cache policy. The version number is solely for the browser's cache key.

## Components

### 1. `app/middleware.py` — `CacheControlMiddleware`

A Starlette `BaseHTTPMiddleware` subclass:

- **Input:** ASGI request/response
- **Logic:** Match `request.url.path` against a list of (pattern, cache_directive) rules
- **Output:** Sets `Cache-Control` header on the response, or does nothing for non-matching paths
- **Rules table** (ordered, first match wins):

| Path prefix | Cache-Control |
|-------------|--------------|
| `/static/js/htmx.min.js` | `public, max-age=31536000, immutable` |
| `/static/` | `public, max-age=2592000, immutable` |
| `/uploads/thumbnails/` | `public, max-age=604800` |
| `/uploads/videos/` | `public, max-age=86400` |

- **Fallthrough:** Any path not matching the above gets no `Cache-Control` header (already works as-is).

### 2. Template update — `app/templates/base.html`

Add `?v=2` query parameter to existing static asset references:

- `/static/css/style.css` → `/static/css/style.css?v=2`
- `/static/js/upload.js` → `/static/js/upload.js?v=2`
- `/static/js/clipper.js` → `/static/js/clipper.js?v=2`
- `/static/js/htmx.min.js` — no version needed (1-year immutable, never changes)

### 3. App integration — `app/main.py`

Add middleware registration:

```python
from app.middleware import CacheControlMiddleware
app.add_middleware(CacheControlMiddleware)
```

### Files NOT changed

- Upload routes (`app/routes/videos.py`) — thumbnail and video paths match middleware rules
- StaticFiles mount — unchanged
- Any other template — no changes needed

## Data Flow

```
1. Browser requests /static/css/style.css?v=3
2. Request enters Starlette pipeline
3. CacheControlMiddleware inspects path = "/static/css/style.css"
4. Matches "/static/" rule → Cache-Control: public, max-age=2592000, immutable
5. Response flows to StaticFiles mount → file content returned
6. Middleware adds Cache-Control header to response
7. Browser receives file + cache header
8. Browser caches for 30 days
9. Subsequent visits: served from disk cache (zero network)

When file changes: bump ?v=3 → ?v=4 in template
→ Browser sees different URL → fresh fetch
```

## Error Handling

- **Middleware failure:** Caught by try/except. Response is returned without cache headers. App doesn't break. Logged at WARNING level.
- **Missing files:** StaticFiles returns 404. Middleware still applies cache headers (harmless — 404s with cache headers are irrelevant).
- **Unknown file types:** Fall through to default `no-cache`. Safe.
- **Version param format:** The middleware ignores query params entirely. Invalid values like `?v=abc` are harmless.

## Testing Strategy

Three scenarios via `TestClient`:

1. **Cache header correctness by path:**
   - `GET /static/js/htmx.min.js` → `Cache-Control` contains `max-age=31536000`
   - `GET /static/css/style.css` → `Cache-Control` contains `max-age=2592000`
   - `GET /uploads/thumbnails/foo.webp` → `Cache-Control` contains `max-age=604800`
   - `GET /uploads/videos/bar.mp4` → `Cache-Control` contains `max-age=86400`
   - `GET /` → no `Cache-Control` header (or `no-cache`)

2. **Query parameter invariance:**
   - `GET /static/css/style.css` and `GET /static/css/style.css?v=42` return same `Cache-Control`

3. **Non-static routes unaffected:**
   - API routes and HTML pages do not get cache headers

## Effort Estimate

| Task | Effort |
|------|--------|
| Create `app/middleware.py` with `CacheControlMiddleware` | ~15 min |
| Update `app/main.py` to register middleware | ~2 min |
| Update `app/templates/base.html` with versioned URLs | ~2 min |
| Write tests for middleware | ~10 min |
| **Total** | **~30 min** |
