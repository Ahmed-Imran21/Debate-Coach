import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.db.database import get_db
from app.models.user import User


_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        _bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected an access token",
        )

    try:
        user_id = uuid.UUID(payload.get("sub"))

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

    return user


def _optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        _bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User | None:
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def require_admin(
    current_user: User | None = Depends(_optional_user),
) -> User:
    """
    Every route in app/routes/admin.py depends on this — it is the
    security boundary; web/middleware.ts's /admin gate is UX.

    Anyone who isn't an admin — no token, a bad or expired token,
    or a signed-in non-admin — gets FastAPI's own "no such route"
    response, byte for byte, so the admin routes can't be told
    apart from paths that don't exist. A 401 or 403 here would
    confirm they do. See also main.py's 405 handler and
    redirect_slashes=False, which close the same gap for wrong
    methods and trailing slashes.

    Email, not a role column, on purpose — there is exactly one
    admin (the person running this env), controlled entirely by
    an env var so adding/removing an admin is a config change,
    not a migration or a deploy.
    """

    if (
        current_user is None
        or current_user.email.lower() not in settings.admin_emails_list
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    return current_user
