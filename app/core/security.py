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
) -> str:

    now = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
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


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id,
        timedelta(
            days=settings.refresh_token_expire_days
        ),
        "refresh",
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
