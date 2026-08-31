import enum
from datetime import datetime
from sqlalchemy import DateTime,Enum,ForeignKey,Integer,String,Text,func
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base
class ImportJob(Base):
    __tablename__="import_jobs";id:Mapped[int]=mapped_column(primary_key=True);uploaded_by:Mapped[int]=mapped_column(ForeignKey("users.id"));file_name:Mapped[str]=mapped_column(String(255));upload_type:Mapped[str]=mapped_column(String(30));total_rows:Mapped[int]=mapped_column(Integer);success_count:Mapped[int]=mapped_column(Integer);failed_count:Mapped[int]=mapped_column(Integer);pending_section_references:Mapped[int]=mapped_column(Integer,default=0,server_default="0");errors_json:Mapped[str]=mapped_column(Text,default="[]");results_json:Mapped[str]=mapped_column(Text,default="[]",server_default="[]");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class AuditLog(Base):
    __tablename__="audit_logs";id:Mapped[int]=mapped_column(primary_key=True);actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"));action:Mapped[str]=mapped_column(String(100));entity_type:Mapped[str]=mapped_column(String(100));entity_id:Mapped[int]=mapped_column();details:Mapped[str]=mapped_column(Text);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class NotificationStatus(str,enum.Enum):PENDING="pending";SENT="sent";FAILED="failed"
class Notification(Base):
    __tablename__="notifications";id:Mapped[int]=mapped_column(primary_key=True);recipient_type:Mapped[str]=mapped_column(String(20));recipient_id:Mapped[int]=mapped_column(Integer);channel:Mapped[str]=mapped_column(String(10));subject:Mapped[str]=mapped_column(String(255));body:Mapped[str]=mapped_column(Text);html_body:Mapped[str|None]=mapped_column(Text,nullable=True);status:Mapped[NotificationStatus]=mapped_column(Enum(NotificationStatus),default=NotificationStatus.PENDING);related_entity:Mapped[str|None]=mapped_column(String(50),nullable=True);related_entity_id:Mapped[int|None]=mapped_column(Integer,nullable=True);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());sent_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
