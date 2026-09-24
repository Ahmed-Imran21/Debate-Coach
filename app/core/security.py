from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


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


def hash_password(password: str) -> str:
    return pwd_context.hash(_prepare(password))


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return pwd_context.verify(
        _prepare(plain_password),
        hashed_password,
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
