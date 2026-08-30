from pydantic import BaseModel, ConfigDict, EmailStr, Field
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
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
    avatar_url: str | None = None

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
