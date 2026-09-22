from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app.routes.deps import require_admin
from app.schemas.admin import (
    AdminStatsOut,
    AdminWhoAmIOut,
    KeyUsageOut,
    StorageUsageOut,
)
from app.services import engine, storage
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
