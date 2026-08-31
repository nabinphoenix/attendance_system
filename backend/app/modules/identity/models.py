import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    COORDINATOR = "coordinator"
    PARENT = "parent"
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    avatar_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Profile photos are private account data. Store the validated image bytes
    # with the account so uploads survive redeploys and do not depend on the
    # instance filesystem or optional object storage.
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def avatar_url(self) -> str | None:
        """A same-origin URL keeps profile images working through the frontend proxy."""
        return f"/api/v1/profile-media/{self.avatar_key}" if self.avatar_key else None
