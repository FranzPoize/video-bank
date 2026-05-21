"""Server-rendered signup, email verification, login, and logout routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.dependencies import (
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PATH,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    get_current_user_optional,
)
from app.services import account_service, auth_service, email_service, invitation_service, session_service
from app.templates import get_i18n, templates


router = APIRouter()


def _current_user_context(current_session: dict | None = None) -> dict:
    """Return template auth context for public auth pages."""
    return {
        "current_user": current_session["user"] if current_session else None,
        "current_account": None,
    }


def _verification_url(request: Request, token: str, invitation_token: str | None = None) -> str:
    """Build an absolute email verification URL for outgoing emails."""
    url = str(request.url_for("verify_email")) + f"?token={token}"
    if invitation_token:
        url += f"&invitation_token={invitation_token}"
    return url


@router.get("/signup")
async def signup_form(request: Request, current_session=Depends(get_current_user_optional)):
    """Render the signup form."""
    i18n = get_i18n(request)
    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            **i18n,
            **_current_user_context(current_session),
            "email": "",
            "invitation_token": request.query_params.get("invitation_token", ""),
        },
    )


@router.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    invitation_token: str = Form(""),
    db=Depends(get_db),
):
    """Create an unverified user, email a verification token, and show confirmation."""
    i18n = get_i18n(request)
    _ = i18n["_"]
    try:
        user = await auth_service.create_unverified_user(db, email, password)
        token = await auth_service.create_email_verification_token(db, user["id"])
        if invitation_token:
            invitation = await invitation_service.get_pending_invitation_by_token(db, invitation_token)
            if user["normalized_email"] != invitation["invited_normalized_email"]:
                raise ValueError("Invitation email mismatch")
        verification_url = _verification_url(request, token, invitation_token or None)
        if invitation_token:
            email_service.send_verification_email(
                user["email"],
                verification_url,
                invitation_url=str(request.url_for("accept_invitation_form")) + f"?token={invitation_token}",
            )
        else:
            email_service.send_verification_email(user["email"], verification_url)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                **i18n,
                **_current_user_context(),
                "email": email,
                "invitation_token": invitation_token,
                "error": _("auth.signup.error"),
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "verify_email.html",
        {
            **i18n,
            **_current_user_context(),
            "status": "sent",
            "email": user["email"],
            "invitation_token": invitation_token,
        },
    )


@router.get("/verify-email", name="verify_email")
async def verify_email(
    request: Request,
    token: str = "",
    invitation_token: str = "",
    db=Depends(get_db),
    current_session=Depends(get_current_user_optional),
):
    """Verify an email token and create the initial account/admin membership."""
    i18n = get_i18n(request)
    if not token:
        status = "failure"
    else:
        try:
            await auth_service.verify_email_token(
                db,
                token,
                create_account=True,
                invitation_token=invitation_token or None,
            )
            status = "success"
        except ValueError:
            status = "failure"

    return templates.TemplateResponse(
        request,
        "verify_email.html",
        {
            **i18n,
            **_current_user_context(current_session),
            "status": status,
            "invitation_token": invitation_token,
        },
        status_code=200,
    )


@router.get("/login")
async def login_form(request: Request, current_session=Depends(get_current_user_optional)):
    """Render the login form."""
    i18n = get_i18n(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {**i18n, **_current_user_context(current_session), "email": ""},
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    """Validate credentials, create a session cookie, and redirect home."""
    i18n = get_i18n(request)
    _ = i18n["_"]
    try:
        user = await auth_service.validate_login_credentials(db, email, password)
    except ValueError as exc:
        error_key = "auth.login.unverified" if str(exc) == auth_service.UNVERIFIED_LOGIN_ERROR else "auth.login.invalid"
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                **i18n,
                **_current_user_context(),
                "email": email,
                "error": _(error_key),
                "show_resend_placeholder": error_key == "auth.login.unverified",
            },
            status_code=400,
        )

    accounts = await account_service.list_accounts_for_user(db, user["id"])
    active_account_id = accounts[0]["id"] if accounts else None
    session = await session_service.create_session(db, user["id"], active_account_id=active_account_id)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session["token"],
        httponly=SESSION_COOKIE_HTTPONLY,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
        path=SESSION_COOKIE_PATH,
    )
    return response


@router.post("/logout")
async def logout(request: Request, db=Depends(get_db)):
    """Revoke the current session, clear the cookie, and redirect to login."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await session_service.revoke_session(db, token)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path=SESSION_COOKIE_PATH, samesite=SESSION_COOKIE_SAMESITE)
    return response
