import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.templates import get_i18n_context, templates


def _layout_test_app(context: dict | None = None) -> FastAPI:
    """Create a focused app that renders the shared base layout."""
    app = FastAPI()

    @app.get("/")
    async def layout_route(request: Request):
        return templates.TemplateResponse(
            request,
            "base.html",
            {**get_i18n_context("en"), **(context or {})},
        )

    return app


class TestAuthenticatedLayoutNavigation:
    """Tests for auth-aware links in the shared base layout."""

    @pytest.mark.asyncio
    async def test_anonymous_layout_shows_login_and_signup(self):
        """Anonymous route contexts render login/signup links without auth controls."""
        transport = ASGITransport(app=_layout_test_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert 'href="/login"' in response.text
        assert 'href="/signup"' in response.text
        assert 'action="/logout"' not in response.text
        assert 'data-testid="auth-user-indicator"' not in response.text

    @pytest.mark.asyncio
    async def test_authenticated_layout_shows_account_user_and_logout(self):
        """Authenticated route contexts render user/account indicators and logout."""
        transport = ASGITransport(
            app=_layout_test_app(
                {
                    "current_user": {"email": "alice@example.com"},
                    "current_account": {"display_name": "Team Alpha"},
                }
            )
        )
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert 'data-testid="auth-user-indicator"' in response.text
        assert "alice@example.com" in response.text
        assert "Team Alpha" in response.text
        assert 'action="/logout"' in response.text
        assert 'href="/login"' not in response.text
        assert 'href="/signup"' not in response.text
