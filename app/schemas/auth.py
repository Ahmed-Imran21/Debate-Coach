from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    # The two sign-up checkboxes. Optional in the schema so a missing
    # one gets the plain "please agree" message from the route rather
    # than a validation error; the route decides whether they're
    # required (settings.signup_consent_required).
    accepted_privacy_policy: bool | None = None
    accepted_terms: bool | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
