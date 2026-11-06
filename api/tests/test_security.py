from __future__ import annotations

import hashlib
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)


def test_passwords_use_argon2id_and_verify() -> None:
    hashed = hash_password("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password!!", hashed)
    assert not password_needs_rehash(hashed)


def test_legacy_scrypt_hashes_still_verify_and_ask_for_an_upgrade() -> None:
    salt = b"0123456789abcdef"
    digest = hashlib.scrypt(b"old-password", salt=salt, n=2**14, r=8, p=1)
    legacy = f"scrypt${salt.hex()}${digest.hex()}"

    assert verify_password("old-password", legacy)
    assert not verify_password("other", legacy)
    assert password_needs_rehash(legacy)


def test_garbage_hashes_never_verify() -> None:
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "scrypt$zz$zz")


def test_access_tokens_carry_subject_version_and_type() -> None:
    claims = decode_access_token(create_access_token("7", token_version=3))

    assert (claims["sub"], claims["ver"], claims["typ"]) == ("7", 3, "access")
    assert claims["jti"]


def test_expired_and_foreign_tokens_are_rejected() -> None:
    expired = create_access_token("7", expires_delta=timedelta(seconds=-5))
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(expired)

    forged = jwt.encode({"sub": "7", "typ": "access", "exp": 9999999999}, "another-secret-key-of-32-chars-or-more", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)

    wrong_type = jwt.encode({"sub": "7", "typ": "refresh", "exp": 9999999999}, settings.secret_key, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(wrong_type)


def test_refresh_tokens_are_random_and_stored_hashed() -> None:
    first_raw, first_hash = new_refresh_token()
    second_raw, _ = new_refresh_token()

    assert first_raw != second_raw and len(first_raw) >= 60
    assert first_hash == hash_token(first_raw) and first_hash != first_raw
