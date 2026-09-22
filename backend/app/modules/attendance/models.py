import enum
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CIDR, INET
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.tenancy import CollegeOwned


CIDR_TYPE = CIDR().with_variant(String(64), "sqlite")
INET_TYPE = INET().with_variant(String(45), "sqlite")


class AttendanceStatus(str, enum.Enum): PRESENT="present"; LATE="late"; ABSENT="absent"; LEAVE="leave"; BUNK="bunk"
class AttendanceMethod(str, enum.Enum): QR_GEOFENCE="qr_geofence"; FINALIZATION="finalization"; MANUAL="manual"
class CheckInAttemptStatus(str, enum.Enum): ACCEPTED="accepted"; PENDING="pending"; CONFIRMED="confirmed"; REJECTED="rejected"
class CampusNetwork(CollegeOwned, Base):
    __tablename__ = "campus_networks"
    __table_args__ = (Index("ix_campus_networks_college_active", "college_id", "is_active"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    cidr: Mapped[str] = mapped_column(CIDR_TYPE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttendanceRecord(CollegeOwned, Base):
    __tablename__="attendance_records"
    __table_args__=(UniqueConstraint("class_session_id","student_id",name="uq_attendance_session_student"),Index("ix_attendance_session_student","class_session_id","student_id"))
    id:Mapped[int]=mapped_column(primary_key=True)
    class_session_id:Mapped[int]=mapped_column(ForeignKey("class_sessions.id"))
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    method:Mapped[AttendanceMethod]=mapped_column(Enum(AttendanceMethod))
    ip_status:Mapped[str]=mapped_column(String(20),default="unknown",server_default="unknown")
    network_method:Mapped[str]=mapped_column(String(20),default="public_ip",server_default="public_ip")
    check_in_time:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class AttendanceChange(CollegeOwned, Base):
    __tablename__="attendance_changes"
    id:Mapped[int]=mapped_column(primary_key=True)
    attendance_record_id:Mapped[int]=mapped_column(ForeignKey("attendance_records.id"))
    before_status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    after_status:Mapped[AttendanceStatus]=mapped_column(Enum(AttendanceStatus))
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    changed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class CheckInAttempt(CollegeOwned, Base):
    __tablename__="check_in_attempts"
    __table_args__=(Index("ix_check_in_attempt_session_status","class_session_id","status"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    class_session_id:Mapped[int]=mapped_column(ForeignKey("class_sessions.id",ondelete="CASCADE"))
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    status:Mapped[CheckInAttemptStatus]=mapped_column(Enum(CheckInAttemptStatus))
    failure_reason:Mapped[str|None]=mapped_column(String(50),nullable=True)
    qr_version:Mapped[int|None]=mapped_column(Integer,nullable=True)
    latitude:Mapped[float|None]=mapped_column(Float,nullable=True)
    longitude:Mapped[float|None]=mapped_column(Float,nullable=True)
    accuracy_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    distance_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    allowed_radius_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    client_ip:Mapped[str|None]=mapped_column(INET_TYPE,nullable=True)
    ip_status:Mapped[str]=mapped_column(String(20),default="unknown",server_default="unknown")
    confirm_client_ip:Mapped[str|None]=mapped_column(INET_TYPE,nullable=True)
    confirm_ip_status:Mapped[str|None]=mapped_column(String(20),nullable=True)
    geofence_pass:Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    reviewed_by:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    decision_reason:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
class AttendanceChallenge(CollegeOwned, Base):
    __tablename__="attendance_challenges"
    __table_args__=(
        UniqueConstraint("class_session_id","qr_version",name="uq_attendance_challenge_session_qr_version"),
        Index("ix_attendance_challenges_session_active","class_session_id","revoked_at","expires_at"),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    class_session_id:Mapped[int]=mapped_column(ForeignKey("class_sessions.id",ondelete="CASCADE"))
    qr_version:Mapped[int]=mapped_column(Integer)
    qr_nonce:Mapped[str]=mapped_column(String(64))
    code_hash:Mapped[str]=mapped_column(String(64))
    code_ciphertext:Mapped[str]=mapped_column(Text)
    created_by:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class PendingAttendanceVerification(CollegeOwned, Base):
    __tablename__="pending_attendance_verifications"
    __table_args__=(
        UniqueConstraint("token_hash",name="uq_pending_attendance_verification_token"),
        Index("ix_pending_attendance_verification_student","student_id","class_session_id","expires_at"),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    token_hash:Mapped[str]=mapped_column(String(64))
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    class_session_id:Mapped[int]=mapped_column(ForeignKey("class_sessions.id",ondelete="CASCADE"))
    attendance_challenge_id:Mapped[int]=mapped_column(ForeignKey("attendance_challenges.id",ondelete="CASCADE"))
    qr_version:Mapped[int]=mapped_column(Integer)
    latitude:Mapped[float|None]=mapped_column(Float,nullable=True)
    longitude:Mapped[float|None]=mapped_column(Float,nullable=True)
    accuracy_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    distance_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    allowed_radius_meters:Mapped[float|None]=mapped_column(Float,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    failed_attempts:Mapped[int]=mapped_column(Integer,default=0,server_default="0")
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    invalidated_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class LeaveRequest(CollegeOwned, Base):
    __tablename__="leave_requests"
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"))
    leave_date:Mapped[date]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),default="pending")
