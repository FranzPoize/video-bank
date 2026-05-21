"""
Deterministic email delivery boundary for account emails.

This checkpoint intentionally avoids real network email delivery. The default
console provider gives developers a visible preview while returning structured,
stable send metadata that tests can assert against safely.
"""

from __future__ import annotations

import hashlib
import logging
import os


logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = "Video Bank <no-reply@video-bank.local>"
DEFAULT_DELIVERY_MODE = "console"
SUPPORTED_DELIVERY_MODES = {"console", "log", "disabled"}


def send_email(
    recipient: str,
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
    from_email: str | None = None,
    delivery_mode: str | None = None,
) -> dict:
    """Send an email through the configured development boundary.

    Returns a structured result with deterministic message metadata. Raises
    ValueError for invalid email inputs and RuntimeError for unsupported or
    failing delivery infrastructure configuration.
    """
    normalized_recipient = _validate_email(recipient, "recipient")
    clean_subject = _validate_required_text(subject, "Subject")
    clean_text_body = _validate_required_text(text_body, "Email body")
    clean_html_body = html_body.strip() if html_body and html_body.strip() else None
    sender = (from_email or DEFAULT_FROM_EMAIL).strip()
    mode = (delivery_mode or os.getenv("EMAIL_DELIVERY_MODE") or DEFAULT_DELIVERY_MODE).strip().lower()

    if mode not in SUPPORTED_DELIVERY_MODES:
        raise RuntimeError(f"Unsupported email delivery mode: {mode}")

    message_id = _message_id(sender, normalized_recipient, clean_subject, clean_text_body, clean_html_body)
    preview = _build_preview(clean_text_body, clean_html_body)
    accepted = mode != "disabled"

    result = {
        "accepted": accepted,
        "provider": mode,
        "message_id": message_id,
        "recipient": normalized_recipient,
        "sender": sender,
        "subject": clean_subject,
        "preview": preview,
    }

    try:
        if mode == "console":
            _print_development_email(result, clean_text_body, clean_html_body)
        elif mode == "log":
            logger.info(
                "Development email preview: to=%s subject=%s message_id=%s preview=%s",
                normalized_recipient,
                clean_subject,
                message_id,
                preview,
            )
    except Exception as exc:  # pragma: no cover - defensive infrastructure boundary
        logger.error("Email delivery boundary failed: %s", exc)
        raise RuntimeError("Email delivery boundary failed") from exc

    if accepted:
        logger.info(
            "Email queued: provider=%s to=%s subject=%s message_id=%s",
            mode,
            normalized_recipient,
            clean_subject,
            message_id,
        )
    else:
        logger.info(
            "Email delivery disabled: to=%s subject=%s message_id=%s",
            normalized_recipient,
            clean_subject,
            message_id,
        )

    return result


def send_verification_email(
    recipient: str,
    verification_url: str,
    *,
    invitation_url: str | None = None,
    delivery_mode: str | None = None,
) -> dict:
    """Send an email verification message. Returns the send result."""
    url = _validate_required_text(verification_url, "Verification URL")
    invitation_text = ""
    if invitation_url is not None:
        invitation_text = (
            "\n\nAfter verification, your pending account invitation will be accepted."
            f"\nInvitation link: {_validate_required_text(invitation_url, 'Invitation URL')}"
        )
    result = send_email(
        recipient,
        "Verify your Video Bank email",
        "Welcome to Video Bank. Verify your email by opening this link:\n\n"
        f"{url}\n\n"
        f"{invitation_text}\n\n"
        "If you did not request this, you can ignore this email.",
        delivery_mode=delivery_mode,
    )
    result["kind"] = "verification"
    return result


def send_invitation_email(
    recipient: str,
    *,
    inviter_email: str,
    account_name: str,
    invitation_url: str,
    delivery_mode: str | None = None,
) -> dict:
    """Send an account invitation email. Returns the send result."""
    inviter = _validate_email(inviter_email, "inviter")
    clean_account_name = _validate_required_text(account_name, "Account name")
    url = _validate_required_text(invitation_url, "Invitation URL")

    result = send_email(
        recipient,
        f"Invitation to join {clean_account_name} on Video Bank",
        f"{inviter} invited you to join {clean_account_name} on Video Bank.\n\n"
        f"Accept the invitation here:\n\n{url}\n\n"
        "If you were not expecting this invitation, you can ignore this email.",
        delivery_mode=delivery_mode,
    )
    result["kind"] = "invitation"
    return result


def _validate_email(value: str, label: str) -> str:
    """Normalize and validate a simple email address. Returns normalized email."""
    email = (value or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError(f"A valid {label} email is required")
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError(f"A valid {label} email is required")
    return email


def _validate_required_text(value: str, label: str) -> str:
    """Validate required text input. Returns stripped text."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{label} cannot be empty")
    return cleaned


def _message_id(
    sender: str,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str | None,
) -> str:
    """Build a deterministic message identifier for test-safe assertions."""
    digest = hashlib.sha256(
        "\n".join([sender, recipient, subject, text_body, html_body or ""]).encode("utf-8")
    ).hexdigest()[:24]
    return f"dev-{digest}@video-bank.local"


def _build_preview(text_body: str, html_body: str | None) -> str:
    """Return a compact preview suitable for logs and tests."""
    source = html_body or text_body
    return " ".join(source.split())[:500]


def _print_development_email(result: dict, text_body: str, html_body: str | None) -> None:
    """Print a development email preview to stdout."""
    print("--- Video Bank development email ---")
    print(f"To: {result['recipient']}")
    print(f"From: {result['sender']}")
    print(f"Subject: {result['subject']}")
    print(f"Message-ID: {result['message_id']}")
    print("")
    print(text_body)
    if html_body:
        print("")
        print("HTML preview:")
        print(html_body)
    print("--- end development email ---")
