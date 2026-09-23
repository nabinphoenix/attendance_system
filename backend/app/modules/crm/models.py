import enum
from datetime import datetime
from sqlalchemy import DateTime,Enum,ForeignKey,Index,Integer,String,Text,and_,func,text
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.core.database import Base
from app.core.tenancy import CollegeOwned
class CaseStatus(str,enum.Enum):OPEN="open";IN_PROGRESS="in_progress";RESOLVED="resolved";CLOSED="closed"
class CasePriority(str,enum.Enum):LOW="low";MEDIUM="medium";HIGH="high"
class StudentCase(CollegeOwned, Base):
    __tablename__="student_cases"
    id:Mapped[int]=mapped_column(primary_key=True);student_id:Mapped[int]=mapped_column(ForeignKey("students.id"));trigger_type:Mapped[str]=mapped_column(String(50));scope_type:Mapped[str]=mapped_column(String(50));scope_id:Mapped[int]=mapped_column(Integer);status:Mapped[CaseStatus]=mapped_column(Enum(CaseStatus,values_callable=lambda items:[x.value for x in items]),default=CaseStatus.OPEN);priority:Mapped[CasePriority]=mapped_column(Enum(CasePriority,values_callable=lambda items:[x.value for x in items]),default=CasePriority.LOW);assigned_to:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True);opened_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());closed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);last_evaluated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now());interactions:Mapped[list["CaseInteraction"]]=relationship(back_populates="case",cascade="all, delete-orphan")
    __table_args__=(Index("uq_active_case","student_id","trigger_type","scope_type","scope_id",unique=True,postgresql_where=text("status IN ('open', 'in_progress')"),sqlite_where=text("status IN ('open', 'in_progress')")),)
class CaseInteraction(CollegeOwned, Base):
    __tablename__="case_interactions";id:Mapped[int]=mapped_column(primary_key=True);case_id:Mapped[int]=mapped_column(ForeignKey("student_cases.id"));staff_id:Mapped[int]=mapped_column(ForeignKey("users.id"));channel:Mapped[str]=mapped_column(String(30));notes:Mapped[str]=mapped_column(Text);outcome:Mapped[str|None]=mapped_column(Text,nullable=True);logged_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());case:Mapped[StudentCase]=relationship(back_populates="interactions")
from sqlalchemy import CheckConstraint, Float

class AttendanceThresholdAlertStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class AttendanceThresholdAlert(CollegeOwned, Base):
    """Tracks one below-threshold period for a student and attendance scope."""

    __tablename__ = "attendance_threshold_alerts"
    __table_args__ = (
        CheckConstraint(
            "module_offering_id IS NOT NULL OR subject_id IS NOT NULL",
            name="ck_attendance_alert_scope",
        ),
        Index(
            "uq_active_attendance_alert_module",
            "student_id",
            "module_offering_id",
            unique=True,
            postgresql_where=text("status = 'active' AND module_offering_id IS NOT NULL"),
            sqlite_where=text("status = 'active' AND module_offering_id IS NOT NULL"),
        ),
        Index(
            "uq_active_attendance_alert_subject",
            "student_id",
            "subject_id",
            unique=True,
            postgresql_where=text("status = 'active' AND subject_id IS NOT NULL"),
            sqlite_where=text("status = 'active' AND subject_id IS NOT NULL"),
        ),
        Index("ix_attendance_alert_student_context", "student_id", "cohort_semester_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    module_offering_id: Mapped[int | None] = mapped_column(ForeignKey("module_offerings.id"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    cohort_semester_id: Mapped[int | None] = mapped_column(ForeignKey("cohort_semesters.id"), nullable=True)
    threshold: Mapped[float] = mapped_column(Float)
    percentage_at_trigger: Mapped[float] = mapped_column(Float)
    attended_sessions: Mapped[int] = mapped_column(Integer)
    eligible_sessions: Mapped[int] = mapped_column(Integer)
    status: Mapped[AttendanceThresholdAlertStatus] = mapped_column(
        Enum(AttendanceThresholdAlertStatus, values_callable=lambda values: [value.value for value in values]),
        default=AttendanceThresholdAlertStatus.ACTIVE,
    )
    first_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    email_queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
