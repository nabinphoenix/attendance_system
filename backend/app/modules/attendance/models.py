import enum
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class AttendanceStatus(str, enum.Enum): PRESENT="present"; LATE="late"; ABSENT="absent"; LEAVE="leave"; BUNK="bunk"
class AttendanceMethod(str, enum.Enum): QR_GEOFENCE="qr_geofence"; FINALIZATION="finalization"; MANUAL="manual"
class AttendanceRecord(Base):
    __tablename__="attendance_records"
    __table_args__=(UniqueConstraint("class_session_id","student_id",name="uq_attendance_session_student"),Index("ix_attendance_session_student","class_session_id","student_id"))
    id:Mapped[int]=mapped_column(primary_key=True)
    class_session_id:Mapped[int]=mapped_column(ForeignKey("class_sessions.id"))
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    method:Mapped[AttendanceMethod]=mapped_column(Enum(AttendanceMethod))
    check_in_time:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class AttendanceChange(Base):
    __tablename__="attendance_changes"
    id:Mapped[int]=mapped_column(primary_key=True)
    attendance_record_id:Mapped[int]=mapped_column(ForeignKey("attendance_records.id"))
    before_status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    after_status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    changed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class LeaveRequest(Base):
    __tablename__="leave_requests"
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    leave_date:Mapped[date]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),default="pending")
