from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user import UserOut


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
