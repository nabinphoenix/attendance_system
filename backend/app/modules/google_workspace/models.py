from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import CollegeOwned


class GoogleWorkspaceConnection(CollegeOwned, Base):
    __tablename__ = "google_workspace_connections"
    __table_args__ = (UniqueConstraint("college_id", name="uq_google_workspace_connections_college"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connected_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    google_email: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    granted_scopes: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleWorkspaceResource(CollegeOwned, Base):
    __tablename__ = "google_workspace_resources"
    __table_args__ = (
        UniqueConstraint("college_id", "google_resource_id", name="uq_google_workspace_resource_college_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("google_workspace_connections.id"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    google_resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GoogleOAuthAttempt(Base):
    """Single-use, hashed OAuth state bound to the initiating admin and college."""

    __tablename__ = "google_oauth_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
