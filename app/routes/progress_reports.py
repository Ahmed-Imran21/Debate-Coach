"""
AI progress report over the user's last 3, 5 or 7 completed
sessions, at most one per user per UTC day. Logic in
app/services/progress_reports.py; the LLM call in
progress_report/service.py.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.progress_report import ProgressReport
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.progress_report import LatestProgressReportOut, ProgressReportCreate, ProgressReportOut
from app.services import engine
from app.services import progress_reports as reports
from progress_report.service import ProgressReportFailed

router = APIRouter(prefix="/progress-reports", tags=["progress-reports"])


def _out(report: ProgressReport) -> ProgressReportOut:
    return ProgressReportOut(
        id=report.id,
        report_date=report.report_date,
        created_at=report.created_at,
        session_count_requested=report.session_count_requested,
        session_count_used=report.session_count_used,
        bullets=list(report.content.get("bullets", [])),
    )


@router.post("", response_model=ProgressReportOut, status_code=status.HTTP_201_CREATED)
def create_progress_report(
    payload: ProgressReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressReportOut:
    try:
        report = reports.generate(db, current_user, payload.session_count, engine.get_api_client(), now=reports.utc_now)

    except reports.AlreadyGeneratedToday as exc:
        wait = max(1, math.ceil((exc.next_at - reports.utc_now()).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "You've already generated today's progress report. The next one is available from "
                f"{exc.next_at:%Y-%m-%d %H:%M} UTC."
            ),
            headers={"Retry-After": str(wait)},
        )

    except reports.NotEnoughSessions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A progress report compares sessions, so it needs at least 2 completed sessions. Record another speech first.",
        )

    except ProgressReportFailed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The report couldn't be written just now. This didn't use up today's report; try again shortly.",
        )

    return _out(report)


@router.get("/latest", response_model=LatestProgressReportOut)
def get_latest_progress_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LatestProgressReportOut:
    now = reports.utc_now()
    latest = reports.latest_report(db, current_user)
    used_today = latest is not None and latest.report_date == now.date()

    return LatestProgressReportOut(
        report=_out(latest) if latest else None,
        can_generate=not used_today,
        next_available_at=reports.next_available_at(now) if used_today else None,
    )
