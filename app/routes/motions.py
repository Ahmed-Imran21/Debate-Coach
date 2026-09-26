"""
GET /v1/motions: the practice motions a new session can pick, from
app/motions.py (the single source of truth), so the frontend never
hard-codes the list. Signed-in users only: it's only used by the
recorder, and there's no reason to add a public route.
"""

from fastapi import APIRouter, Depends

from app.models.user import User
from app.motions import active_motions
from app.routes.deps import get_current_user
from app.schemas.session import MotionOut

router = APIRouter(prefix="/motions", tags=["motions"])


@router.get("", response_model=list[MotionOut])
def list_motions(current_user: User = Depends(get_current_user)) -> list[MotionOut]:
    return [MotionOut(id=m.id, title=m.title, description=m.description) for m in active_motions()]
