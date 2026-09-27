import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

BestCategory = Literal["overall", "quantitative", "argumentation", "rebuttal", "structure", "persuasion", "logic"]


class ProfileUpdate(BaseModel):
    """
    Only the fields sent are changed. A blank or null username or bio
    clears it. The format rules are checked in app/services/profile.py,
    which gives each field its own message.
    """

    model_config = ConfigDict(extra="forbid")

    username: StrictStr | None = None
    bio: StrictStr | None = None
    weekly_goal: StrictInt | None = None
    time_zone: StrictStr | None = None


class StreakOut(BaseModel):
    current: int
    longest: int
    # False with current > 0: practised yesterday, not yet today.
    practised_today: bool


class WeekOut(BaseModel):
    # Completed sessions this Monday-to-Sunday week (user's time zone);
    # can exceed the goal.
    completed: int
    goal: int
    goal_met: bool
    starts_on: date
    ends_on: date


class PersonalBestOut(BaseModel):
    category: BestCategory
    # All None when the category has no score yet.
    score: float | None
    session_id: uuid.UUID | None
    title: str | None
    created_at: datetime | None


class ProfileOut(BaseModel):
    """The current user's own profile. Never served for anyone else."""

    first_name: str
    last_name: str
    username: str | None
    bio: str | None
    weekly_goal: int
    time_zone: str | None
    completed_sessions: int
    streak: StreakOut
    week: WeekOut
    personal_bests: list[PersonalBestOut]
