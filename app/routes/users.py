from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user import DeleteAccountRequest, UserOut
from app.services import storage


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Fallback for LastSeenMiddleware (app/core/last_seen.py),
    which only fires on requests that hit some other endpoint —
    a tab sitting on a page that makes no other API calls (e.g.
    the report page, post-load) would otherwise look inactive.
    web/ pings this every ~60s while a tab is open and signed in.

    No debounce here unlike the middleware: this endpoint IS the
    debounce (the frontend controls the interval), and a single
    UPDATE is cheap enough to not need a second layer of
    throttling on top of the caller's own ~60s cadence.
    """

    current_user.last_seen_at = datetime.now(timezone.utc)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Re-authenticates with the current password (never trust a
    frontend "confirmed" flag — this is the actual authorization
    check, not the modal's typed "DELETE"), then permanently
    deletes every row and stored object this user owns.

    Storage before the database row, matching delete_session's
    same ordering (sessions.py) and for the same reason: if
    storage.delete_prefix raises, nothing has been committed and
    the account still exists, so the request just fails cleanly
    and can be retried. Deleting the user row after is a single
    local operation that's already ON DELETE CASCADE to every
    session, video-analysis and metric row it owns (see each
    model's ForeignKey("users.id", ondelete="CASCADE")), so
    nothing else needs to be deleted explicitly here.

    No separate "invalidate every session" step is needed either:
    get_current_user and the /auth/refresh route both 401 a token
    whose user_id no longer resolves to a row, so every access and
    refresh token this account ever issued — on any device — stops
    working the moment this commits, without needing a revocation
    list.
    """

    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    storage.delete_prefix(f"users/{current_user.id}/")

    db.delete(current_user)
    db.commit()
