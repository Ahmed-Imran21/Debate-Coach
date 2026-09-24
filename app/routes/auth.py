import uuid

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)


router = APIRouter(prefix="/auth", tags=["auth"])

# Same algorithm and cost as real hashes, of a random string nobody
# knows. Checked against when the email doesn't exist so an unknown
# email costs the same ~300ms bcrypt verify as a wrong password.
_TIMING_EQUALIZER_HASH = "$2b$12$Fj0fpUtj14hdPYxjNXhGvuqbLt4mcpRmYSxoPwX1CnQXJ6bvMBGmu"


def _tokens_for(
    user: User,
    session_start: int | None = None,
) -> TokenResponse:
    """
    session_start: None for signup/login (a brand-new session);
    the original session's start time, carried through unchanged,
    for a refresh (see refresh() below) — that's what lets the
    absolute session-lifetime cap be enforced independent of the
    per-token idle expiry, which resets on every reissue.
    """
    # The /admin gate cookie is set by the frontend itself now
    # (web/app/api/session/route.ts), on its own domain; a cookie set
    # here could never reach it in production (*.run.app and
    # *.vercel.app are both public suffixes).
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id), session_start),
    )


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:

    email = payload.email.strip().lower()

    existing = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email already has an account.",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return _tokens_for(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:

    email = payload.email.strip().lower()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    password_ok = verify_password(
        payload.password,
        user.password_hash if user is not None else _TIMING_EQUALIZER_HASH,
    )

    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return _tokens_for(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:

    try:
        decoded = decode_token(payload.refresh_token)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected a refresh token",
        )

    try:
        # The subject is stored as a string in the token but
        # the primary key column is a UUID. Coerce here so the
        # lookup matches deps.get_current_user exactly.
        user_id = uuid.UUID(decoded.get("sub"))

    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        ) from exc

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Absolute session lifetime: the per-token "exp" jose already
    # checked above (via decode_token) only enforces an idle
    # timeout, because every reissue resets it to a fresh
    # refresh_token_expire_days from now — a session refreshed
    # regularly would otherwise never actually end. session_start
    # is never reset, so it's what lets a continuously-active
    # session still be forced to a real login eventually. Falls
    # back to this token's own "iat" for a refresh token minted
    # before this claim existed, which is exactly the right value:
    # that token's actual issue time.
    session_start = decoded.get("session_start", decoded.get("iat"))
    session_age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        session_start, tz=timezone.utc
    )

    if session_age > timedelta(days=settings.refresh_token_expire_days):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please log in again.",
        )

    return _tokens_for(user, session_start=session_start)
