from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.services import profile as profiles


router = APIRouter(prefix="/profile", tags=["profile"])


# There is deliberately no route that takes a user id or a username:
# both endpoints only ever read or write the signed-in user's own
# profile and sessions.


@router.get("", response_model=ProfileOut)
def read_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return profiles.build_profile(db, current_user)


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    PUT, not PATCH: the API's CORS policy allows exactly the methods
    web/ already used (GET, POST, PUT, DELETE), and a test pins PATCH
    as refused. Still a partial update: only the fields sent change
    (username, bio, weekly_goal, time_zone). Returns the whole updated
    profile, since the goal and time zone change the streak and week
    figures. 422 with a per-field
    message when something is invalid, nothing saved; 409 when the
    username is taken.
    """

    changes = {field: getattr(payload, field) for field in payload.model_fields_set}

    try:
        profiles.update_profile(db, current_user, changes)
    except profiles.UsernameTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.message) from None
    except profiles.ProfileFieldError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.message) from None

    return profiles.build_profile(db, current_user)
