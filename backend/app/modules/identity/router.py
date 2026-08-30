import hashlib
import io
from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import func, select
from app.core.dependencies import DbSession, get_current_user, require_role
from app.modules.operations.service import log_audit
from app.core.security import hash_password, verify_password
from app.modules.academic.models import InvitationStatus, Student, StudentInvitation
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import LoginRequest, PasswordChange, ProfileUpdate, TokenResponse, UserRead, UserUpdate
from app.modules.identity.service import authenticate, issue_token
from app.core.config import settings
from app.core.profile_media import ProfileMediaNotFound, ProfileMediaStore, ProfileMediaUnavailable

router = APIRouter(tags=["identity"])
# Local development uses the repository folder. Production services can supply
# a writable state directory when S3 storage has not been configured.
PROFILE_MEDIA_DIR = Path(settings.profile_media_local_directory) if settings.profile_media_local_directory else Path(__file__).resolve().parents[3] / "uploads" / "profiles"
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
PROFILE_IMAGE_TYPES = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


def get_profile_media_store() -> ProfileMediaStore:
    return ProfileMediaStore(
        bucket=settings.profile_media_bucket,
        prefix=settings.profile_media_prefix,
        region=settings.profile_media_region,
        local_directory=PROFILE_MEDIA_DIR,
    )


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

@router.get("/auth/me", response_model=UserRead)
def me(user: Annotated[User, Depends(get_current_user)]) -> User: return user

@router.patch("/auth/me", response_model=UserRead)
def update_profile(payload: ProfileUpdate, user: Annotated[User, Depends(get_current_user)], db: DbSession) -> User:
    name = payload.name.strip() if payload.name is not None else None
    email = str(payload.email).lower() if payload.email is not None else None
    if name is not None and not name:
        raise HTTPException(422, "Name is required")

    email_changed = email is not None and email != user.email.lower()
    if email_changed:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(422, "Enter your current password to change your sign-in email")
        if db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user.id)):
            raise HTTPException(409, "An account with this email already exists")

    before: dict[str, str] = {}
    after: dict[str, str] = {}
    if name is not None and name != user.name:
        before["name"] = user.name
        after["name"] = name
        user.name = name
    if email_changed:
        before["email"] = user.email
        after["email"] = email
        user.email = email
    if not after:
        raise HTTPException(422, "Provide a different name or email address")

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student:
        if "name" in after:
            student.name = name
        if "email" in after:
            student.email = email
    log_audit(db, user.id, "user.profile_updated", "user", user.id, before, after)
    db.commit(); db.refresh(user)
    return user

@router.post("/auth/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChange, user: Annotated[User, Depends(get_current_user)], db: DbSession) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(422, "Your current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(422, "Choose a password you have not used for this change")
    user.password_hash = hash_password(payload.new_password)
    log_audit(db, user.id, "user.password_changed", "user", user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/auth/me/avatar", response_model=UserRead)
async def upload_avatar(
    image: Annotated[UploadFile, File(description="A JPEG, PNG, or WEBP profile image")],
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> User:
    contents = await image.read()
    if not contents or len(contents) > MAX_PROFILE_IMAGE_BYTES:
        raise HTTPException(422, "Profile images must be between 1 byte and 5 MB")
    try:
        decoded = Image.open(io.BytesIO(contents))
        image_format = decoded.format
        decoded.verify()
        decoded = Image.open(io.BytesIO(contents))
        if decoded.width > 4096 or decoded.height > 4096:
            raise HTTPException(422, "Profile images must be no larger than 4096 pixels on either side")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "The uploaded file is not a valid image") from exc
    if image_format not in PROFILE_IMAGE_TYPES:
        raise HTTPException(415, "Upload a JPEG, PNG, or WEBP image")
    suffix, media_type = PROFILE_IMAGE_TYPES[image_format]
    avatar_key = f"{uuid4().hex}.{suffix}"
    media_store = get_profile_media_store()
    try:
        media_store.save(avatar_key, contents, media_type)
    except ProfileMediaUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    old_key = user.avatar_key
    user.avatar_key = avatar_key
    log_audit(db, user.id, "user.avatar_updated", "user", user.id, {"avatar_key": old_key}, {"avatar_key": avatar_key})
    try:
        db.commit(); db.refresh(user)
    except Exception:
        db.rollback()
        try:
            media_store.delete(avatar_key)
        except ProfileMediaUnavailable:
            pass
        raise
    if old_key:
        try:
            media_store.delete(old_key)
        except ProfileMediaUnavailable:
            # The new image and database update are already durable. Keeping an
            # old object is preferable to turning a successful upload into a 5xx.
            pass
    return user

@router.get("/profile-media/{avatar_key}")
def profile_media(avatar_key: str, _: Annotated[User, Depends(get_current_user)]) -> Response:
    if Path(avatar_key).name != avatar_key:
        raise HTTPException(404, "Profile image not found")
    try:
        image = get_profile_media_store().read(avatar_key)
    except ProfileMediaNotFound as exc:
        raise HTTPException(404, "Profile image not found")
    except ProfileMediaUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )

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
