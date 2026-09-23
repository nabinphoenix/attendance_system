from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool
    is_locked: bool = False
    failed_login_attempts: int = 0
    locked_at: datetime | None = None
    avatar_url: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    active_college_id: int | None = None

class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    # An email address is used to sign in, so changing it requires proving the
    # account holder still knows their current password.
    current_password: str | None = Field(default=None, max_length=128)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetChallenge(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class ResetPasswordRequest(ResetChallenge):
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        # bcrypt only uses 72 bytes; do not silently accept truncated passwords.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        if len(value.strip()) < 8 or len(set(value)) < 3 or value.lower() in {
            "password", "password1", "password123", "12345678", "123456789", "qwerty123", "abcdefgh",
        }:
            raise ValueError("Choose a stronger password of at least 8 characters")
        return value

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
