from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id: Mapped[int] = mapped_column(primary_key=True)
class AttendanceChange(Base):
    __tablename__ = "attendance_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
