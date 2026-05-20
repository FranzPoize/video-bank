"""
Tests for the deterministic email service boundary.

The email service is intentionally network-free for this checkpoint: it returns
structured send results and logs/prints enough information for development.
"""

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

    def test_unknown_delivery_mode_is_infrastructure_failure(self):
        """Unknown configured delivery modes fail as infrastructure errors."""
        with pytest.raises(RuntimeError, match="Unsupported email delivery mode"):
            email_service.send_email(
                "user@example.com",
                "Subject",
                "Body",
                delivery_mode="smtp",
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
