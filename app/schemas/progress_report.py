import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProgressReportCreate(BaseModel):
    # Anything else is a 422 before the route runs.
    session_count: Literal[3, 5, 7]


class ProgressReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_date: date
    created_at: datetime
    session_count_requested: int
    session_count_used: int
    bullets: list[str]


class LatestProgressReportOut(BaseModel):
    # The most recent report, of any day; None if there's never been one.
    report: ProgressReportOut | None
    # False once today's (UTC) report exists; next_available_at then
    # says when the next one is allowed (the next UTC midnight).
    can_generate: bool
    next_available_at: datetime | None
