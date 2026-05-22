"""
Tests for the deterministic email service boundary.

The email service is intentionally network-free for this checkpoint: it returns
structured send results and logs/prints enough information for development.
"""

from unittest.mock import patch

import pytest

from app.services import email_service


class TestEmailService:
    """Tests for generic email sending."""

    def test_send_email_returns_deterministic_result(self, capsys, caplog):
        """send_email returns stable structured data and writes a dev preview."""
        caplog.set_level("INFO")

        first = email_service.send_email(
            "User@Example.COM",
            "Verify your email",
            "Please verify: https://example.test/verify?token=abc",
        )
        second = email_service.send_email(
            "user@example.com",
            "Verify your email",
            "Please verify: https://example.test/verify?token=abc",
        )

        assert first["accepted"] is True
        assert first["provider"] == "console"
        assert first["recipient"] == "user@example.com"
        assert first["subject"] == "Verify your email"
        assert first["message_id"] == second["message_id"]
        assert "verify" in first["preview"].lower()

        output = capsys.readouterr().out
        assert "Video Bank development email" in output
        assert "user@example.com" in output

        info_logs = [r for r in caplog.records if "Email queued" in r.getMessage()]
        assert len(info_logs) == 2

    def test_send_email_rejects_invalid_inputs(self):
        """send_email raises ValueError for validation errors."""
        with pytest.raises(ValueError, match="valid recipient email"):
            email_service.send_email("not-an-email", "Subject", "Body")

        with pytest.raises(ValueError, match="Subject cannot be empty"):
            email_service.send_email("user@example.com", "   ", "Body")

        with pytest.raises(ValueError, match="Email body cannot be empty"):
            email_service.send_email("user@example.com", "Subject", "")

    def test_disabled_mode_returns_not_accepted_without_network(self, capsys):
        """disabled mode is explicit and still returns a structured result."""
        result = email_service.send_email(
            "user@example.com",
            "Subject",
            "Body",
            delivery_mode="disabled",
        )

        assert result["accepted"] is False
        assert result["provider"] == "disabled"
        assert result["recipient"] == "user@example.com"
        assert capsys.readouterr().out == ""

    def test_smtp_mode_sends_gmail_message(self, monkeypatch):
        """smtp mode sends through Gmail with the configured app credentials."""
        monkeypatch.setenv("EMAIL_ACCOUNT", "sender@gmail.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "app-password")

        with patch("app.services.email_service.smtplib.SMTP") as mock_smtp:
            smtp_client = mock_smtp.return_value.__enter__.return_value

            result = email_service.send_email(
                "User@Example.COM",
                "Subject",
                "Plain body",
                html_body="<p>HTML body</p>",
                delivery_mode="smtp",
            )

        mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
        smtp_client.starttls.assert_called_once_with()
        smtp_client.login.assert_called_once_with("sender@gmail.com", "app-password")
        smtp_client.send_message.assert_called_once()
        message = smtp_client.send_message.call_args.args[0]
        assert message["From"] == "Videobank <sender@gmail.com>"
        assert message["To"] == "user@example.com"
        assert message["Subject"] == "Subject"
        assert "Plain body" in message.get_body(preferencelist=("plain",)).get_content()
        assert "HTML body" in message.get_body(preferencelist=("html",)).get_content()

        assert result["accepted"] is True
        assert result["provider"] == "smtp"
        assert result["recipient"] == "user@example.com"
        assert result["sender"] == "Videobank <sender@gmail.com>"
        assert result["subject"] == "Subject"
        assert result["preview"] == "<p>HTML body</p>"
        assert result["message_id"].startswith("dev-")

    def test_smtp_mode_can_be_selected_from_environment(self, monkeypatch):
        """EMAIL_DELIVERY_MODE=smtp is accepted as a supported delivery mode."""
        monkeypatch.setenv("EMAIL_DELIVERY_MODE", "smtp")
        monkeypatch.setenv("EMAIL_ACCOUNT", "sender@gmail.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "app-password")

        with patch("app.services.email_service.smtplib.SMTP") as mock_smtp:
            result = email_service.send_email("user@example.com", "Subject", "Body")

        assert result["provider"] == "smtp"
        mock_smtp.return_value.__enter__.return_value.send_message.assert_called_once()

    def test_smtp_mode_requires_gmail_configuration(self, monkeypatch):
        """smtp mode fails fast when Gmail credentials are not configured."""
        monkeypatch.delenv("EMAIL_ACCOUNT", raising=False)
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

        with pytest.raises(RuntimeError, match="EMAIL_ACCOUNT and EMAIL_PASSWORD are required"):
            email_service.send_email(
                "user@example.com",
                "Subject",
                "Body",
                delivery_mode="smtp",
            )

    def test_unknown_delivery_mode_is_infrastructure_failure(self):
        """Unknown configured delivery modes fail as infrastructure errors."""
        with pytest.raises(RuntimeError, match="Unsupported email delivery mode"):
            email_service.send_email(
                "user@example.com",
                "Subject",
                "Body",
                delivery_mode="unknown",
            )


class TestEmailTemplates:
    """Tests for verification and invitation email helpers."""

    def test_send_verification_email_builds_expected_message(self):
        """Verification helper includes the verification URL in the result preview."""
        result = email_service.send_verification_email(
            "new-user@example.com",
            "https://video-bank.test/verify-email?token=abc123",
        )

        assert result["accepted"] is True
        assert result["kind"] == "verification"
        assert result["recipient"] == "new-user@example.com"
        assert "verify" in result["subject"].lower()
        assert "https://video-bank.test/verify-email?token=abc123" in result["preview"]

    def test_send_invitation_email_builds_expected_message(self):
        """Invitation helper includes inviter, account name, and invitation URL."""
        result = email_service.send_invitation_email(
            "invitee@example.com",
            inviter_email="owner@example.com",
            account_name="Family Videos",
            invitation_url="https://video-bank.test/invitations/accept?token=xyz",
        )

        assert result["accepted"] is True
        assert result["kind"] == "invitation"
        assert result["recipient"] == "invitee@example.com"
        assert "Family Videos" in result["subject"]
        assert "owner@example.com" in result["preview"]
        assert "https://video-bank.test/invitations/accept?token=xyz" in result["preview"]

    def test_template_helpers_validate_urls(self):
        """Template helpers reject missing action URLs with ValueError."""
        with pytest.raises(ValueError, match="Verification URL cannot be empty"):
            email_service.send_verification_email("user@example.com", "")

        with pytest.raises(ValueError, match="Invitation URL cannot be empty"):
            email_service.send_invitation_email(
                "user@example.com",
                inviter_email="owner@example.com",
                account_name="Account",
                invitation_url=" ",
            )
