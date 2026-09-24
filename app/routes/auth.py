import uuid

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
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

ADMIN_SESSION_COOKIE = "dc_admin_session"

# Same algorithm and cost as real hashes, of a random string nobody
# knows. Checked against when the email doesn't exist so an unknown
# email costs the same ~300ms bcrypt verify as a wrong password.
_TIMING_EQUALIZER_HASH = "$2b$12$Fj0fpUtj14hdPYxjNXhGvuqbLt4mcpRmYSxoPwX1CnQXJ6bvMBGmu"


def _tokens_for(
    user: User,
    response: Response,
    session_start: int | None = None,
) -> TokenResponse:
    """
    session_start: None for signup/login (a brand-new session);
    the original session's start time, carried through unchanged,
    for a refresh (see refresh() below) — that's what lets the
    absolute session-lifetime cap be enforced independent of the
    per-token idle expiry, which resets on every reissue.
    """
    access_token = create_access_token(str(user.id))
    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=create_refresh_token(str(user.id), session_start),
    )

    # Admin-only, additive: the real session still lives in
    # localStorage exactly as before (every existing API call is
    # unaffected). This cookie exists purely so web/middleware.ts
    # can gate /admin server-side — middleware has no access to
    # localStorage. Not set for non-admin users, so a non-admin
    # session carries no extra cookie at all.
    #
    # samesite="none" (not "lax"): production puts the frontend
    # (Vercel) and this backend (Cloud Run) on genuinely different
    # domains, not just different ports the way local dev is —
    # "lax" gets silently dropped across a real cross-site set,
    # the same failure mode as the missing credentials: "include"
    # this cookie needed on the frontend fetch (see lib/api.ts).
    # Unconditional rather than environment-branched: "none" is
    # strictly less restrictive than "lax" (sent everywhere "lax"
    # would send it, plus cross-site), so it already worked over
    # plain http://localhost in local testing and needs no
    # environment detection. Requires secure=True, already set.
    # Safe to loosen here specifically because nothing server-side
    # ever reads this cookie from the request — it's httpOnly and
    # consumed only by middleware.ts, which reads it off the
    # incoming same-origin browser request and re-sends it itself
    # as a Bearer header; there's no request-forgery surface to
    # protect against by keeping it site-restricted.
    if user.email.lower() in settings.admin_emails_list:
        response.set_cookie(
            key=ADMIN_SESSION_COOKIE,
            value=access_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=settings.access_token_expire_minutes * 60,
            path="/",
        )
    else:
        # Covers the case where ADMIN_EMAILS changes and a
        # previously-admin user logs in again post-demotion.
        response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")

    return tokens


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    payload: SignupRequest,
    response: Response,
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

    return _tokens_for(user, response)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
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

    return _tokens_for(user, response)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    response: Response,
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

    return _tokens_for(user, response, session_start=session_start)
