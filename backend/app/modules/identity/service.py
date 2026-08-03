from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import create_access_token, verify_password
from app.modules.identity.models import User

def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email))
    return user if user and verify_password(password, user.password_hash) else None

def issue_token(user: User) -> str:
    return create_access_token(str(user.id), user.role.value)
