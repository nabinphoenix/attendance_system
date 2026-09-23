"""Atomic fixed-window throttling persisted across application workers/restarts."""
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.attendance.network import get_client_ip
from app.modules.identity.models import AuthRateLimit


def client_key(request: Request) -> str:
    return get_client_ip(request) or (request.client.host if request.client else "unknown")


def consume(db: Session, bucket: str, identity: str, limit: int, seconds: int, *, reject: bool = True) -> bool:
    now = datetime.now(UTC)
    key = hmac.new(settings.jwt_secret_key.encode(), f"{bucket}:{identity}".encode(), hashlib.sha256).hexdigest()
    # Expired buckets are disposable; cleanup keeps the table bounded by the window.
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(AuthRateLimit).values(key=key, count=1, expires_at=now + timedelta(seconds=seconds))
    statement = statement.on_conflict_do_update(
        index_elements=[AuthRateLimit.key],
        set_={"count": case((AuthRateLimit.count < limit + 1, AuthRateLimit.count + 1), else_=AuthRateLimit.count)},
    ).returning(AuthRateLimit.count)
    count = db.scalar(statement)
    # Persist even when the endpoint rejects credentials or a reset challenge.
    db.commit()
    if count > limit and reject:
        raise HTTPException(429, "Too many requests. Please try again later.", headers={"Retry-After": str(seconds)})
    return count <= limit
