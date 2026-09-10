from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
from app.modules.identity.models import User
from app.modules.platform.models import College
from app.core.tenancy import set_college_scope

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, token: Annotated[str | None, Depends(oauth2_scheme)], db: DbSession) -> User:
    token = token or request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        user_id = int(payload.get("sub", 0))
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid session")
    user = db.scalar(select(User).where(User.id == user_id).execution_options(tenant_bypass=True))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    db.info["actor_id"] = user.id
    scope = None
    if user.role.value == "super_admin":
        college_id = request.headers.get("X-College-ID")
        if request.url.path.startswith("/api/v1/platform"):
            college_id = None
        elif college_id is None and request.url.path.startswith(("/api/v1/auth/", "/api/v1/profile-media/")):
            scope = None
        elif college_id is None:
            raise HTTPException(400, "Select a college before opening its workspace")
        if college_id is not None:
            try:
                scope = int(college_id)
            except ValueError:
                raise HTTPException(422, "Invalid college selection")
    else:
        scope = user.college_id
        if scope is None:
            raise HTTPException(403, "Account has no college assignment")
        selected = request.headers.get("X-College-ID")
        if selected is not None and selected != str(scope):
            raise HTTPException(403, "You cannot access another college")
    college = db.get(College, scope) if scope is not None else None
    if scope is not None and college is None:
        raise HTTPException(403, "College not found")
    if college and not college.is_active and user.role.value != "super_admin":
        raise HTTPException(403, "Your college is inactive. Contact platform support.")
    set_college_scope(db, scope)
    user.college_name = college.name if college else None
    user.active_college_id = scope
    return user


def require_roles(*roles: str) -> Callable:
    def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role.value not in roles and not (user.role.value == "super_admin" and "admin" in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker

def require_role(role: str) -> Callable:
    return require_roles(role)
