import uuid

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.db.database import get_db
from app.models.user import User
from app.routes.deps import require_admin
from app.schemas.admin import (
    AdminDeleteUserRequest,
    AdminStatsOut,
    AdminUserOut,
    AdminUserPageOut,
    AdminWhoAmIOut,
    KeyUsageOut,
    StorageUsageOut,
)
from app.services import admin_users, engine, storage
from app.services.accounts import AccountBusyError, delete_user_account
from app.services.key_usage import get_usage_snapshot


router = APIRouter(prefix="/admin", tags=["admin"])

ACTIVE_WINDOW = timedelta(minutes=5)


@router.get("/whoami", response_model=AdminWhoAmIOut)
def whoami(
    current_user: User = Depends(require_admin),
) -> AdminWhoAmIOut:
    """
    Cheap on purpose: web/middleware.ts calls this on every
    navigation into /admin, so it must not do what /stats does
    (a GCS bucket listing). Reaching this handler at all already
    means require_admin passed — the body only exists to give
    middleware a 200 to check for.
    """

    return AdminWhoAmIOut(email=current_user.email, is_admin=True)


@router.get("/stats", response_model=AdminStatsOut)
def stats(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminStatsOut:

    active_cutoff = datetime.now(timezone.utc) - ACTIVE_WINDOW

    active_users = (
        db.query(func.count(User.id))
        .filter(User.last_seen_at > active_cutoff)
        .scalar()
    )

    total_signups = db.query(func.count(User.id)).scalar()

    api_client = engine.get_api_client()
    keys = [
        KeyUsageOut(**entry)
        for entry in get_usage_snapshot(api_client)
    ]

    used_bytes = storage.total_bytes_used()
    used_gb = used_bytes / (1024 ** 3)
    quota_gb = settings.admin_storage_quota_gb

    return AdminStatsOut(
        active_users=active_users or 0,
        total_signups=total_signups or 0,
        keys=keys,
        storage=StorageUsageOut(
            used_bytes=used_bytes,
            used_gb=round(used_gb, 3),
            quota_gb=quota_gb,
            remaining_gb=round(max(0.0, quota_gb - used_gb), 3),
        ),
    )


@router.get("/users", response_model=AdminUserPageOut)
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=100),
    sort: admin_users.Sort = "newest",
    limit: int = admin_users.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> AdminUserPageOut:
    """
    One page of users, newest signup first (or most recently seen),
    optionally filtered by a substring of email, first or last name.
    Pass next_cursor back as ?cursor= for the next page. limit is
    clamped to 1..100 rather than rejected, like GET /v1/sessions.

    require_admin runs before any query parameter is validated, so a
    non-admin sending a malformed cursor or limit still gets the same
    plain 404 as any path that doesn't exist.
    """

    try:
        rows, next_cursor = admin_users.list_users(
            db, sort=sort, search=search, limit=limit, cursor=cursor
        )
    except admin_users.InvalidCursorError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor. Start again from the first page.",
        ) from None

    admins = set(settings.admin_emails_list)
    return AdminUserPageOut(
        users=[
            AdminUserOut(**vars(row), is_admin=row.email.lower() in admins)
            for row in rows
        ],
        next_cursor=next_cursor,
    )


async def _delete_request_password(
    request: Request,
    _admin: User = Depends(require_admin),
) -> str:
    """
    The delete's body, read only after require_admin has passed.
    Declaring it as a normal body parameter would let FastAPI parse
    it first — before any dependency runs — so a non-admin sending
    malformed JSON would get a 422 where a nonexistent path gives a
    404, revealing the route. (DELETE /v1/users/me does exactly that,
    harmlessly: it isn't a hidden route.)
    """
    try:
        return AdminDeleteUserRequest.model_validate_json(await request.body()).password
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from None


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": AdminDeleteUserRequest.model_json_schema()}},
        }
    },
)
def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    password: str = Depends(_delete_request_password),
    db: Session = Depends(get_db),
) -> None:
    """
    Force-delete another user's account and everything it owns,
    through the same delete_user_account() as the self-service delete.

    Re-authenticates with the calling admin's own password (never the
    target's), first — before the target is even looked up. Every
    later step says something: 404 that the id doesn't exist, 409 that
    it's the caller, an admin, or mid-analysis. Without the password
    this answers 401 and nothing else, whatever the target, so a
    stolen admin session alone can neither delete anyone nor learn
    anything here. Same order as DELETE /v1/users/me: password, then
    everything else.

    Refused, with 409, for:
    - the calling admin's own account: self-deletion goes through
      DELETE /v1/users/me, which re-checks the password, so a stolen
      admin session can't delete the admin's own account with none.
    - any other admin: admin rights come from ADMIN_EMAILS, not the
      database, so deleting the account wouldn't revoke them (signing
      up again with the same email restores them). Removing the email
      from ADMIN_EMAILS is the step that actually demotes someone;
      after that their account is an ordinary one this route deletes.
    """

    if not verify_password(password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    target = db.get(User, user_id)

    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You can't delete your own account from here. Use Delete "
                "account on your practice page, which asks for your password."
            ),
        )

    if target.email.lower() in settings.admin_emails_list:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This account is an admin. Remove its email from "
                "ADMIN_EMAILS first; then it can be deleted here."
            ),
        )

    try:
        delete_user_account(db, target)
    except AccountBusyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "One of this user's sessions is still being analyzed. "
                "Try again once it finishes."
            ),
        ) from None
