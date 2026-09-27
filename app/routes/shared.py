"""
GET /v1/shared/{token}: the PUBLIC, unauthenticated read-only report
behind a share link.

- The response is a whitelist (app/schemas/share.py): never audio or
  storage URLs, never the owner, never the session's real id.
- Every failure (malformed, unknown, revoked, replaced, deleted, not
  finished, unreadable) is the same plain 404, byte for byte the same
  as a route that doesn't exist, so nothing tells a guesser why.
- Never cached publicly, never indexed, and the token never leaks via
  Referer from this response.
- Rate-limited per client more tightly than the rest of the API
  (app/main.py, PerClientRateLimitMiddleware path_limits). Tokens are
  256-bit random, so enumeration isn't possible anyway.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.share import SharedReportOut
from app.services import shares

router = APIRouter(prefix="/shared", tags=["shared"])

PUBLIC_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
}


@router.get("/{token}", response_model=SharedReportOut)
def get_shared_report(token: str, response: Response, db: Session = Depends(get_db)) -> SharedReportOut:
    session = shares.resolve(db, token)
    report = shares.build_shared_report(db, session) if session is not None else None
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found", headers=PUBLIC_HEADERS)

    response.headers.update(PUBLIC_HEADERS)
    return report
