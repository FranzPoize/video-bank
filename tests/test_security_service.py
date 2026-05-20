"""
Tests for authentication security helpers.

Run with: pytest tests/test_security_service.py -v
"""

import pytest

from app.services import security_service


class TestEmailNormalization:
    """Tests for email normalization."""

    def test_normalize_email_strips_and_lowercases(self):
        """Email normalization strips surrounding spaces and lowercases."""
        assert security_service.normalize_email("  User.Name@Example.COM  ") == "user.name@example.com"

    def test_normalize_email_preserves_internal_content(self):
        """Email normalization keeps plus tags and internal punctuation."""
        assert security_service.normalize_email("Person+Tag@Example.com") == "person+tag@example.com"


class TestPasswordHashing:
    """Tests for PBKDF2 password hashing and verification."""

    def test_password_hash_verifies_correct_password(self):
        """Password hashes verify the original password."""
        password_hash = security_service.hash_password("correct horse battery staple")

        assert security_service.verify_password("correct horse battery staple", password_hash) is True

    def test_password_hash_rejects_wrong_password(self):
        """Password verification rejects an incorrect password."""
        password_hash = security_service.hash_password("correct horse battery staple")

        assert security_service.verify_password("wrong password", password_hash) is False

    def test_password_hashes_are_salted(self):
        """Hashing the same password twice creates different salted hashes."""
        first_hash = security_service.hash_password("same password")
        second_hash = security_service.hash_password("same password")

        assert first_hash != second_hash
        assert security_service.verify_password("same password", first_hash) is True
        assert security_service.verify_password("same password", second_hash) is True

    def test_malformed_password_hash_returns_false(self):
        """Malformed stored password hashes fail closed."""
        assert security_service.verify_password("password", "not-a-valid-hash") is False

    @pytest.mark.parametrize("iterations_text", ["0", "-1", "not-an-integer"])
    def test_password_hash_with_invalid_iterations_returns_false(self, iterations_text):
        """Stored hashes with valid field counts but invalid iterations fail closed."""
        stored_hash = f"{security_service.PASSWORD_HASH_ALGORITHM}${iterations_text}$c2FsdA==$a2V5"

        assert security_service.verify_password("password", stored_hash) is False

    @pytest.mark.parametrize(
        "stored_hash",
        [
            f"{security_service.PASSWORD_HASH_ALGORITHM}$1$not base64$a2V5",
            f"{security_service.PASSWORD_HASH_ALGORITHM}$1$c2FsdA==$not base64",
        ],
    )
    def test_password_hash_with_invalid_base64_returns_false(self, stored_hash):
        """Stored hashes with invalid base64 salt or keys fail closed."""
        assert security_service.verify_password("password", stored_hash) is False


class TestTokens:
    """Tests for opaque tokens and safe token hash comparison."""

    def test_create_token_returns_url_safe_opaque_value(self):
        """Generated tokens are non-empty URL-safe opaque strings."""
        token = security_service.create_token()

        assert isinstance(token, str)
        assert len(token) >= 32
        assert "+" not in token
        assert "/" not in token

    def test_create_token_returns_random_values(self):
        """Generated tokens differ between calls."""
        assert security_service.create_token() != security_service.create_token()

    def test_hash_token_is_stable_and_not_plaintext(self):
        """Token hashes are stable but do not store the plaintext token."""
        token = security_service.create_token()

        first_hash = security_service.hash_token(token)
        second_hash = security_service.hash_token(token)

        assert first_hash == second_hash
        assert first_hash != token
        assert len(first_hash) == 64

    def test_compare_hashes_safely_compares_token_hashes(self):
        """Safe comparison accepts matching hashes and rejects mismatches."""
        token = security_service.create_token()
        stored_hash = security_service.hash_token(token)
        other_hash = security_service.hash_token(security_service.create_token())

        assert security_service.compare_hashes(stored_hash, security_service.hash_token(token)) is True
        assert security_service.compare_hashes(stored_hash, other_hash) is False
