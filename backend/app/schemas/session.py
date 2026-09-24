import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.session import SessionStatus


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SessionStatus
    transcription_provider: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SessionCreateResponse(BaseModel):
    id: uuid.UUID
    upload_url: str
    status: SessionStatus
