"""
Permanently deleting a user, shared by the self-service
DELETE /v1/users/me and the admin DELETE /v1/admin/users/{id} so
the two can never drift apart. Authorization is the caller's job;
this only does the deleting.
"""

from sqlalchemy.orm import Session

from app.models.session import DebateSession
from app.models.user import User
from app.services import jobs, storage


class AccountBusyError(Exception):
    """An analysis for one of this user's sessions is still running."""


def delete_user_account(db: Session, user: User) -> None:
    # A pipeline still running would upload its results after the
    # storage prefix below is cleared, leaving recordings in the
    # bucket with no account left to own them.
    session_ids = db.query(DebateSession.id).filter(DebateSession.user_id == user.id)
    if any(jobs.is_running(session_id) for (session_id,) in session_ids):
        raise AccountBusyError()

    # Storage before the row, same as delete_session: if this raises,
    # nothing is committed and the account is intact and retryable.
    storage.delete_prefix(f"users/{user.id}/")

    # Every table with a users.id foreign key (sessions, video_analyses,
    # session_metrics) is ON DELETE CASCADE, so the row is all there
    # is to delete. Every token this account issued stops working once
    # this commits: get_current_user and /auth/refresh 401 a user id
    # that no longer resolves.
    db.delete(user)
    db.commit()
