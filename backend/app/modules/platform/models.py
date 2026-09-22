from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class College(Base):
    __tablename__ = "colleges"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_policy: Mapped[str] = mapped_column(String(10), default="flag", server_default="flag", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("ip_policy IN ('off', 'flag')", name="ck_colleges_ip_policy"),)


class PlatformConfiguration(Base):
    __tablename__ = "platform_configuration"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_name: Mapped[str] = mapped_column(String(150), default="AntimBench")
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allow_college_creation: Mapped[bool] = mapped_column(Boolean, default=True)
