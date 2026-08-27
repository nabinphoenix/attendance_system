import hashlib
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from app.core.dependencies import DbSession, get_current_user, require_role
from app.modules.operations.service import log_audit
from app.core.security import hash_password
from app.modules.academic.models import Batch, InvitationStatus, Section, Student, StudentInvitation
from app.modules.academic.schemas import BatchRead, SectionRead
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import LoginRequest, SignupRequest, TokenResponse, UserRead, UserUpdate
from app.modules.identity.service import authenticate, issue_token
from app.core.config import settings

router = APIRouter(tags=["identity"])


def browser_session(response: Response, user: User) -> TokenResponse:
    token = issue_token(user)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    # Retain the bearer token in the response for documented non-browser API clients.
    return TokenResponse(access_token=token)

def invitation_from_token(db,token:str)->StudentInvitation:
    invitation=db.scalar(select(StudentInvitation).where(StudentInvitation.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    if not invitation:raise HTTPException(404,"Invalid invitation")
    if invitation.status==InvitationStatus.ACTIVATED:raise HTTPException(409,"Invitation has already been used")
    if invitation.status==InvitationStatus.REVOKED:raise HTTPException(410,"Invitation has been revoked")
    expires=invitation.expires_at.replace(tzinfo=UTC) if invitation.expires_at.tzinfo is None else invitation.expires_at
    if expires<=datetime.now(UTC):raise HTTPException(410,"Invitation has expired")
    return invitation
class ActivationRequest(BaseModel): token:str; password:str; name:str|None=None
@router.get("/auth/activate/validate")
def validate_activation(token:str,db:DbSession):
    invite=invitation_from_token(db,token);student=invite.student
    return {"student_name":student.name,"email":student.email,"status":"valid"}
@router.post("/auth/activate",response_model=TokenResponse)
def activate(payload:ActivationRequest,response:Response,db:DbSession):
    if len(payload.password)<8:raise HTTPException(422,"Password must be at least 8 characters")
    invite=invitation_from_token(db,payload.token);student=invite.student
    if student.user_id:raise HTTPException(409,"Student already has an account")
    email=(student.email or "").lower()
    if not email:raise HTTPException(422,"Student profile has no email")
    if db.scalar(select(User.id).where(func.lower(User.email)==email)):raise HTTPException(409,"An account with this email already exists")
    user=User(name=(payload.name or student.name or "Student").strip(),email=email,password_hash=hash_password(payload.password),role=UserRole.STUDENT);db.add(user);db.flush();student.user_id=user.id;student.name=user.name;student.email=user.email;invite.status=InvitationStatus.ACTIVATED;invite.used_at=datetime.now(UTC);log_audit(db,user.id,"student.activated","student",student.id,None,{"invitation_id":invite.id});db.commit();db.refresh(user)
    return browser_session(response,user)

@router.get("/identity/health")
def health() -> dict[str, str]: return {"module": "identity", "status": "ok"}

@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> TokenResponse:
    user = authenticate(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive. Contact an administrator.")
    return browser_session(response,user)

@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: DbSession) -> TokenResponse:
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
    db.add(Student(user_id=user.id, section_id=section.id, roll_number=f"SELF-{user.id:05d}", name=name, email=email))
    log_audit(db, user.id, "student.signup", "user", user.id, None, {"email": user.email, "role": user.role.value})
    db.commit(); db.refresh(user)
    return browser_session(response,user)

@router.get("/public/academic/batches", response_model=list[BatchRead])
def public_batches(db: DbSession):
    return db.scalars(select(Batch).order_by(Batch.name)).all()

@router.get("/public/academic/batches/{batch_id}/sections", response_model=list[SectionRead])
def public_sections(batch_id: int, db: DbSession):
    return db.scalars(select(Section).where(Section.batch_id == batch_id).order_by(Section.name)).all()

@router.get("/auth/me", response_model=UserRead)
def me(user: Annotated[User, Depends(get_current_user)]) -> User: return user

@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

@router.get("/users", response_model=list[UserRead])
def users(user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    return db.scalars(select(User).order_by(User.created_at.desc())).all()

@router.patch("/users/{id}", response_model=UserRead)
def update_user(id: int, payload: UserUpdate, actor: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    account = db.get(User, id)
    if not account: raise HTTPException(404, "User not found")
    changes = payload.model_dump(exclude_none=True)
    if not changes: raise HTTPException(422, "Provide a role or active status")
    if "role" in changes:
        try: role = UserRole(changes["role"])
        except ValueError as exc: raise HTTPException(422, "Invalid role") from exc
        if role == UserRole.STUDENT and not db.scalar(select(Student.id).where(Student.user_id == account.id)):
            matches = db.scalars(select(Student).where(Student.user_id.is_(None), func.lower(Student.email) == account.email.lower())).all()
            if len(matches) != 1:
                raise HTTPException(422, "A student role requires one matching student profile and section. Create or link the student profile first.")
            matches[0].user_id = account.id
            log_audit(db, actor.id, "student.profile_linked", "student", matches[0].id, None, {"source": "admin_role_update", "user_id": account.id})
        account.role = role
    if "is_active" in changes:
        if account.id == actor.id and not changes["is_active"]: raise HTTPException(422, "You cannot deactivate your own account")
        account.is_active = changes["is_active"]
    log_audit(db, actor.id, "user.updated", "user", account.id, None, changes)
    db.commit(); db.refresh(account); return account
