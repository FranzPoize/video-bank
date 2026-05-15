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
