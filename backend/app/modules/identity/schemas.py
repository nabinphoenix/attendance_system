from pydantic import BaseModel, ConfigDict, EmailStr, Field
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    batch_id: int
    section_id: int
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
    name: str = Field(min_length=1, max_length=150)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
