from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class ImportJob(Base):
    __tablename__="import_jobs"
    id:Mapped[int]=mapped_column(primary_key=True)
    status:Mapped[str]=mapped_column(String(30),default="pending")
class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    action:Mapped[str]=mapped_column(String(100))
    entity_type:Mapped[str]=mapped_column(String(100))
    entity_id:Mapped[int]=mapped_column()
    details:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
