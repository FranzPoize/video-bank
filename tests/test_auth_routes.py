"""Route and UI tests for signup, verification, login, and logout."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.dependencies import SESSION_COOKIE_NAME
from app.services import auth_service, security_service, session_service


class TestSignupRoutes:
    """Tests for signup form and submission behavior."""

    @pytest.mark.asyncio
    async def test_signup_form_renders(self, client):
        """GET /signup renders a server-side signup form."""
        response = await client.get("/signup")

        assert response.status_code == 200
        assert "Create your Video Bank account" in response.text
        assert 'method="post" action="/signup"' in response.text
        assert 'name="email"' in response.text
        assert 'name="password"' in response.text

    @pytest.mark.asyncio
    async def test_signup_creates_unverified_user_token_and_sends_email(self, client, db, monkeypatch):
        """POST /signup creates an unverified user/token and calls email_service."""
        sent = {}

        def fake_send_verification_email(recipient, verification_url, *, delivery_mode=None):
            sent["recipient"] = recipient
            sent["verification_url"] = verification_url
            sent["delivery_mode"] = delivery_mode
            return {"accepted": True, "kind": "verification"}

        monkeypatch.setattr(
            "app.routes.auth.email_service.send_verification_email",
            fake_send_verification_email,
        )

        response = await client.post(
            "/signup",
            data={"email": "Owner@Example.com", "password": "correct-password"},
        )

        assert response.status_code == 200
        assert "Check your email" in response.text
        assert sent["recipient"] == "Owner@Example.com"
        assert "/verify-email?token=" in sent["verification_url"]

        user = await auth_service.get_user_by_email(db, "owner@example.com")
        assert user is not None
        assert user["is_email_verified"] == 0
        token_count = await (await db.execute("SELECT COUNT(*) AS count FROM email_verification_tokens")).fetchone()
        assert token_count["count"] == 1


class TestEmailVerificationRoute:
    """Tests for email verification route behavior."""

    @pytest.mark.asyncio
    async def test_valid_token_verifies_user_and_creates_admin_membership(self, client, db):
        """GET /verify-email with a valid token activates direct signup account state."""
        user = await auth_service.create_unverified_user(db, "owner@example.com", "password")
        token = await auth_service.create_email_verification_token(db, user["id"])

        response = await client.get(f"/verify-email?token={token}")

        assert response.status_code == 200
        assert "Your email is verified" in response.text
        verified = await auth_service.get_user_by_id(db, user["id"])
        assert verified["is_email_verified"] == 1

        account = await (
            await db.execute(
                """
                SELECT a.*
                FROM accounts a
                JOIN account_memberships am ON am.account_id = a.id
                WHERE am.user_id = ?
                """,
                (user["id"],),
            )
        ).fetchone()
        membership = await (
            await db.execute(
                "SELECT * FROM account_memberships WHERE user_id = ? AND account_id = ?",
                (user["id"], account["id"]),
            )
        ).fetchone()
        assert account is not None
        assert membership["admin"] == 1

    @pytest.mark.asyncio
    async def test_invalid_token_renders_safe_failure(self, client):
        """Invalid verification tokens show a safe failure message."""
        response = await client.get("/verify-email?token=not-a-real-token")

        assert response.status_code == 200
        assert "This verification link is invalid or expired" in response.text


class TestLoginLogoutRoutes:
    """Tests for login, session cookie creation, and logout."""

    @pytest.mark.asyncio
    async def test_login_form_renders(self, client):
        """GET /login renders a server-side login form."""
        response = await client.get("/login")

        assert response.status_code == 200
        assert "Log in" in response.text
        assert 'method="post" action="/login"' in response.text
        assert 'name="email"' in response.text
        assert 'name="password"' in response.text

    @pytest.mark.asyncio
    async def test_login_rejects_unknown_and_wrong_password_with_same_error(self, client, db):
        """Unknown email and wrong password use the same user-facing error."""
        user = await auth_service.create_unverified_user(db, "known@example.com", "correct-password")
        await db.execute(
            "UPDATE users SET is_email_verified = 1, email_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],),
        )
        await db.commit()

        unknown = await client.post("/login", data={"email": "missing@example.com", "password": "anything"})
        wrong = await client.post("/login", data={"email": "known@example.com", "password": "wrong"})

        assert unknown.status_code == 400
        assert wrong.status_code == 400
        assert "Invalid email or password" in unknown.text
        assert "Invalid email or password" in wrong.text

    @pytest.mark.asyncio
    async def test_login_rejects_unverified_email_with_resend_placeholder(self, client, db):
        """Unverified users cannot login and see the resend placeholder text."""
        await auth_service.create_unverified_user(db, "new@example.com", "correct-password")

        response = await client.post(
            "/login",
            data={"email": "new@example.com", "password": "correct-password"},
        )

        assert response.status_code == 400
        assert "Please verify your email before logging in" in response.text
        assert "Verification email resend will be available soon" in response.text

    @pytest.mark.asyncio
    async def test_login_creates_session_cookie_with_default_active_account(self, client, db):
        """Successful login creates an HttpOnly SameSite=Lax session cookie and redirects."""
        token = await _create_verified_signup(db, "owner@example.com", "correct-password")
        await auth_service.verify_email_token(db, token, create_account=True)

        response = await client.post(
            "/login",
            data={"email": "owner@example.com", "password": "correct-password"},
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        set_cookie = response.headers["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie

        raw_session_token = response.cookies[SESSION_COOKIE_NAME]
        session = await session_service.load_session(db, raw_session_token)
        account = await (
            await db.execute(
                """
                SELECT a.*
                FROM accounts a
                JOIN account_memberships am ON am.account_id = a.id
                JOIN users u ON u.id = am.user_id
                WHERE u.normalized_email = ?
                """,
                ("owner@example.com",),
            )
        ).fetchone()
        assert session is not None
        assert session["active_account_id"] == account["id"]

    @pytest.mark.asyncio
    async def test_logout_revokes_session_and_clears_cookie(self, client, db):
        """POST /logout revokes the current session and clears the browser cookie."""
        token = await _create_verified_signup(db, "owner@example.com", "correct-password")
        await auth_service.verify_email_token(db, token, create_account=True)
        login_response = await client.post(
            "/login",
            data={"email": "owner@example.com", "password": "correct-password"},
        )
        raw_session_token = login_response.cookies[SESSION_COOKIE_NAME]

        response = await client.post("/logout")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert await session_service.load_session(db, raw_session_token) is None
        assert f"{SESSION_COOKIE_NAME}=" in response.headers["set-cookie"]

    @pytest.mark.asyncio
    async def test_base_layout_shows_anonymous_and_authenticated_navigation(self, client, db):
        """Auth pages show signup/login for anonymous users and logout once authenticated."""
        anonymous = await client.get("/login")
        assert "/signup" in anonymous.text
        assert "/login" in anonymous.text
        assert 'hx-get="/api/space"' not in anonymous.text

        token = await _create_verified_signup(db, "owner@example.com", "correct-password")
        await auth_service.verify_email_token(db, token, create_account=True)
        await client.post("/login", data={"email": "owner@example.com", "password": "correct-password"})

        authenticated = await client.get("/login")
        assert "owner@example.com" in authenticated.text
        assert "/logout" in authenticated.text
        assert 'hx-get="/api/space"' in authenticated.text


async def _create_verified_signup(db, email: str, password: str) -> str:
    """Create an unverified user and return a plaintext verification token."""
    user = await auth_service.create_unverified_user(db, email, password)
    stored_user = await auth_service.get_user_by_id(db, user["id"])
    assert security_service.verify_password(password, stored_user["password_hash"])
    return await auth_service.create_email_verification_token(db, user["id"])


def _token_from_verification_url(verification_url: str) -> str:
    """Extract a token from a verification URL."""
    return parse_qs(urlparse(verification_url).query)["token"][0]
