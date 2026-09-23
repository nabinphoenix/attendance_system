import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenancy import set_college_scope
from app.modules.identity.models import User
from app.modules.operations.service import log_audit

LOCKED_MESSAGE = "Your account is locked after multiple unsuccessful login attempts."
# Equalize bcrypt work for an unknown account. This is not a real credential.
_DUMMY_HASH = hash_password("non-user-timing-placeholder")


def clear_login_failures(user: User) -> None:
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_at = None
    user.last_failed_login_at = None


def invalidate_reset(user: User) -> None:
    user.reset_token_hash = None
    user.reset_expires_at = None


def authenticate(db: Session, email: str, password: str) -> User | None:
    # Serialize attempts on this account, including concurrent requests/workers.
    user = db.scalar(select(User).where(User.email == email.strip().lower())
                     .execution_options(tenant_bypass=True).with_for_update())
    if not user:
        verify_password(password, _DUMMY_HASH)
        return None
    set_college_scope(db, user.college_id)
    if user.is_locked:
        raise HTTPException(423, LOCKED_MESSAGE)
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts = min(user.failed_login_attempts + 1, settings.max_failed_login_attempts)
        user.last_failed_login_at = datetime.now(UTC)
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.is_locked = True
            user.locked_at = user.last_failed_login_at
            user.session_version += 1
            log_audit(db, user.id, "auth.account_locked", "user", user.id)
        log_audit(db, user.id, "auth.login_failed", "user", user.id, None, {"attempts": user.failed_login_attempts})
        db.commit()
        if user.is_locked:
            raise HTTPException(423, LOCKED_MESSAGE)
        return None
    clear_login_failures(user)
    return user


def issue_token(user: User) -> str:
    return create_access_token(str(user.id), user.role.value, session_version=user.session_version)


def reset_account(db: Session, token: str) -> User:
    digest = hashlib.sha256(token.encode()).hexdigest()
    user = db.scalar(select(User).where(User.reset_token_hash == digest)
                     .execution_options(tenant_bypass=True).with_for_update())
    expires = user.reset_expires_at if user else None
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if not user or not user.is_active or not expires or expires <= datetime.now(UTC):
        raise HTTPException(400, "This reset link is invalid or expired. Request a new link.")
    set_college_scope(db, user.college_id)
    return user


def unlock_account(db: Session, account: User, actor: User) -> User:
    before = {"is_locked": account.is_locked, "failed_login_attempts": account.failed_login_attempts}
    clear_login_failures(account)
    # An administrator's unlock supersedes any pending recovery challenge.
    invalidate_reset(account)
    event = log_audit(db, actor.id, "auth.account_unlocked", "user", account.id, before, {"is_locked": False})
    event.college_id = account.college_id
    db.commit()
    db.refresh(account)
    return account
