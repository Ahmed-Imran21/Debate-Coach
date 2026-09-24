from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user import DeleteAccountRequest, UserOut
from app.services.accounts import AccountBusyError, delete_user_account


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
    deletes every row and stored object this user owns, through
    the same delete_user_account() the admin force-delete uses.
    """

    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    try:
        delete_user_account(db, current_user)
    except AccountBusyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "One of your sessions is still being analyzed. "
                "Wait for it to finish, then delete your account."
            ),
        ) from None
