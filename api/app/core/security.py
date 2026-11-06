from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

# Argon2id with the library defaults (64 MiB, 3 passes). Old scrypt hashes from the
# single-user version still verify and are upgraded on the next successful login.
_hasher = PasswordHasher()
_LEGACY_SCRYPT_PREFIX = "scrypt$"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith(_LEGACY_SCRYPT_PREFIX):
        return _verify_legacy_scrypt(password, password_hash)
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    if password_hash.startswith(_LEGACY_SCRYPT_PREFIX):
        return True
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def _verify_legacy_scrypt(password: str, password_hash: str) -> bool:
    try:
        _algorithm, salt_hex, digest_hex = password_hash.split("$", maxsplit=2)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(actual, expected)


_dummy_hash: str | None = None


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so unknown emails are not detectable by speed."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("openhunt-dummy-password")
    verify_password(password, _dummy_hash)


def create_access_token(
    subject: str, *, token_version: int = 0, expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {
        "sub": subject,
        "ver": token_version,
        "typ": "access",
        "iat": now,
        "exp": expire,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    claims = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        options={"require": ["exp", "sub", "typ"]},
    )
    if claims.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return claims


def new_refresh_token() -> tuple[str, str]:
    """Return (raw token for the cookie, sha256 hash to store)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
