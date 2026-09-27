import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# Passwords are hashed with bcrypt directly. This replaced passlib's
# CryptContext(schemes=["bcrypt"]), which logged a traceback on every
# cold start (passlib 1.7.4 reads bcrypt.__about__, removed in bcrypt
# 4.1). The behaviour is identical, so every existing hash still
# verifies (tests/fixtures/passlib_hashes.json holds real hashes from
# the passlib code):
# - the same "$2b$" hashes at cost 12;
# - the same 72-byte truncation (_prepare, below, unchanged);
# - the same ValueError for a password containing a NUL character or
#   for a stored hash that isn't a bcrypt hash.
BCRYPT_ROUNDS = 12

# A well-formed bcrypt hash. Checked before bcrypt.checkpw: for a
# value that looks like a bcrypt hash but is cut short, its Rust core
# panics (pyo3 PanicException, not even an Exception) rather than
# raising ValueError as passlib did.
_BCRYPT_HASH = re.compile(r"\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}")

# bcrypt only reads the first 72 bytes of a password and newer
# backends raise rather than truncate silently. Truncating here
# keeps behaviour identical across backend versions, and the
# signup schema caps input length so nothing meaningful is lost.
BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> str:

    encoded = password.encode("utf-8")

    if len(encoded) <= BCRYPT_MAX_BYTES:
        return password

    return encoded[:BCRYPT_MAX_BYTES].decode(
        "utf-8",
        errors="ignore",
    )


def _secret(password: str) -> bytes:
    secret = _prepare(password).encode("utf-8")

    # passlib refused these; bare bcrypt would accept them.
    if b"\x00" in secret:
        raise ValueError("bcrypt does not allow NUL characters in a password.")

    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _secret(password),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS, prefix=b"2b"),
    ).decode("ascii")


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    # A stored value that isn't a bcrypt hash raises ValueError, as
    # passlib did (its UnknownHashError is a ValueError).
    if not isinstance(hashed_password, str) or not _BCRYPT_HASH.fullmatch(hashed_password):
        raise ValueError("The stored password hash is not a bcrypt hash.")

    return bcrypt.checkpw(
        _secret(plain_password),
        hashed_password.encode("utf-8"),
    )


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:

    now = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        **(extra_claims or {}),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: str) -> str:
    return _create_token(
        user_id,
        timedelta(
            minutes=settings.access_token_expire_minutes
        ),
        "access",
    )


def create_refresh_token(
    user_id: str,
    session_start: int | None = None,
) -> str:
    """
    session_start: the unix timestamp the session began, carried
    forward unchanged across every refresh (see app/routes/auth.py
    refresh()). Omit it for a brand-new session (login/signup) —
    it defaults to this token's own iat, which is exactly what a
    first refresh token's session_start should be.

    Each refresh token's own "exp" still resets to a fresh
    refresh_token_expire_days on every reissue (an idle timeout:
    unused for that long and the token itself expires normally).
    session_start is the separate, non-resetting clock that lets
    the route enforce an absolute cap on total session age
    regardless of how often it's refreshed.
    """
    now = datetime.now(timezone.utc)
    return _create_token(
        user_id,
        timedelta(
            days=settings.refresh_token_expire_days
        ),
        "refresh",
        extra_claims={
            "session_start": (
                session_start
                if session_start is not None
                else int(now.timestamp())
            ),
        },
    )


def decode_token(token: str) -> dict[str, Any]:

    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
