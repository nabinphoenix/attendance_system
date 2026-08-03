from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from app.core.dependencies import DbSession, get_current_user
from app.core.security import hash_password
from app.modules.academic.models import Batch, Section, Student
from app.modules.academic.schemas import BatchRead, SectionRead
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import LoginRequest, SignupRequest, TokenResponse, UserRead
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

@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession) -> TokenResponse:
    name = payload.name.strip()
    email = str(payload.email).strip().lower()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Full name is required")
    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password must be at least 8 characters")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    section = db.get(Section, payload.section_id)
    if not section or section.batch_id != payload.batch_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select a valid section for the chosen batch")
    user = User(name=name, email=email, password_hash=hash_password(payload.password), role=UserRole.STUDENT)
    db.add(user); db.flush()
    db.add(Student(user_id=user.id, section_id=section.id, roll_number=f"SELF-{user.id:05d}"))
    db.commit(); db.refresh(user)
    return TokenResponse(access_token=issue_token(user))

@router.get("/academic/batches", response_model=list[BatchRead])
def public_batches(db: DbSession):
    return db.scalars(select(Batch).order_by(Batch.name)).all()

@router.get("/academic/batches/{batch_id}/sections", response_model=list[SectionRead])
def public_sections(batch_id: int, db: DbSession):
    return db.scalars(select(Section).where(Section.batch_id == batch_id).order_by(Section.name)).all()

@router.get("/auth/me", response_model=UserRead)
def me(user: Annotated[User, Depends(get_current_user)]) -> User: return user
