from pydantic import BaseModel, ConfigDict, EmailStr
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
class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
