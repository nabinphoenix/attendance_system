from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.dependencies import DbSession, get_current_user
from app.modules.identity.models import User
from app.modules.identity.schemas import LoginRequest, TokenResponse, UserRead
from app.modules.identity.service import authenticate, issue_token
router = APIRouter(tags=["identity"])
@router.get("/identity/health")
def health() -> dict[str, str]: return {"module": "identity", "status": "ok"}
@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = authenticate(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return TokenResponse(access_token=issue_token(user))
@router.get("/auth/me", response_model=UserRead)
def me(user: Annotated[User, Depends(get_current_user)]) -> User: return user
