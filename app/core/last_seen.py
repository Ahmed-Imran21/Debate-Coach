import logging
import time
import uuid

from datetime import datetime, timezone
from typing import Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import decode_token
from app.db.database import SessionLocal
from app.models.user import User


logger = logging.getLogger(__name__)

# How often (seconds) a given user's last_seen_at is actually
# written, not how often "active" can appear to change — that's
# governed by the 5-minute window the /admin/stats query itself
# uses. Without this, an active tab writes to the users table on
# every single authenticated request, which is most of them.
_TOUCH_INTERVAL_S = 30.0


class LastSeenMiddleware(BaseHTTPMiddleware):
    """
    Touches users.last_seen_at on any authenticated request, so
    "active users right now" reflects real API traffic — not
    just sessions that happen to call POST /heartbeat (that
    endpoint exists as a fallback for a tab that's open but
    making no other calls, e.g. sitting on the report page).

    Runs as middleware rather than inside get_current_user so it
    fires for every authenticated route without every route
    needing to opt in, and so a bad/expired token here fails
    open (no update, request proceeds to the real auth check
    downstream) instead of being one more place a 401 can
    originate from.
    """

    def __init__(self, app):
        super().__init__(app)
        # In-process only, per the same tradeoff PerClientRateLimitMiddleware
        # documents for its own bucket dict: fine for one instance,
        # not shared across instances if this ever scales out.
        self._last_touch: Dict[uuid.UUID, float] = {}

    async def dispatch(self, request: Request, call_next):

        user_id = self._extract_user_id(request)

        if user_id is not None:
            self._maybe_touch(user_id)

        return await call_next(request)

    @staticmethod
    def _extract_user_id(request: Request) -> uuid.UUID | None:

        header = request.headers.get("authorization")

        if not header or not header.lower().startswith("bearer "):
            return None

        token = header[len("bearer "):].strip()

        try:
            payload = decode_token(token)

        except ValueError:
            return None

        if payload.get("type") != "access":
            return None

        try:
            return uuid.UUID(payload.get("sub"))

        except (ValueError, TypeError):
            return None

    def _maybe_touch(self, user_id: uuid.UUID) -> None:

        now = time.monotonic()
        last = self._last_touch.get(user_id)

        if last is not None and now - last < _TOUCH_INTERVAL_S:
            return

        self._last_touch[user_id] = now

        db = SessionLocal()

        try:
            db.query(User).filter(User.id == user_id).update(
                {User.last_seen_at: datetime.now(timezone.utc)}
            )
            db.commit()

        except Exception:
            # Best-effort: never let last_seen tracking break a
            # real request.
            logger.exception(
                "Could not update last_seen_at for user %s",
                user_id,
            )
            db.rollback()

        finally:
            db.close()
