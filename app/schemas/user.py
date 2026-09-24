import uuid

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    created_at: datetime


class DeleteAccountRequest(BaseModel):
    # The frontend also requires typing "DELETE" and only enables
    # the button once that matches, but that's a UI confirmation,
    # not authorization — it travels as nothing more than a normal
    # authenticated DELETE call, which this repo's own access-token
    # theft model (web/lib/api.ts's own comment: XSS reading
    # localStorage) already treats as equivalent to being signed
    # in. The password is the actual re-authentication step, and
    # it's verified server-side against the stored hash, not
    # trusted from any frontend "confirmed" flag.
    password: str
