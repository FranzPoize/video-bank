"""
Security helpers for authentication tokens and password hashes.

Password hashes use stdlib PBKDF2-HMAC-SHA256 with per-password random salts.
Opaque tokens are stored as SHA-256 hashes so plaintext tokens are never persisted.
"""

import base64
import binascii
import hashlib
import secrets


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390_000
PASSWORD_SALT_BYTES = 16
TOKEN_BYTES = 32


def normalize_email(email: str) -> str:
    """Normalize an email address for uniqueness and lookups."""
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Return a salted password hash suitable for database storage."""
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    key_text = base64.urlsafe_b64encode(derived_key).decode("ascii")
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt_text}${key_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored password hash."""
    try:
        algorithm, iterations_text, salt_text, key_text = stored_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False

        iterations = int(iterations_text)
        if iterations <= 0:
            return False

        salt = base64.b64decode(salt_text.encode("ascii"), altchars=b"-_", validate=True)
        expected_key = base64.b64decode(key_text.encode("ascii"), altchars=b"-_", validate=True)
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
    except (ValueError, TypeError, binascii.Error):
        return False

    return secrets.compare_digest(derived_key, expected_key)


def create_token() -> str:
    """Create a random opaque URL-safe token for sessions and email flows."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Hash a plaintext token before storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compare_hashes(left_hash: str, right_hash: str) -> bool:
    """Safely compare two token/password hash strings."""
    return secrets.compare_digest(left_hash, right_hash)
