import enum
from datetime import date,datetime,time
from sqlalchemy import Boolean,CheckConstraint,Date,DateTime,Enum,Float,ForeignKey,Index,Integer,String,Text,Time,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.core.database import Base
class SessionStatus(str,enum.Enum): ACTIVE="active";COMPLETED="completed"
class OverrideStatus(str,enum.Enum): PENDING="pending";APPROVED="approved";REJECTED="rejected"
class TimetableEntry(Base):
    __tablename__="timetable_entries";id:Mapped[int]=mapped_column(primary_key=True);teacher_id:Mapped[int]=mapped_column(ForeignKey("teachers.id"));subject_id:Mapped[int]=mapped_column(ForeignKey("subjects.id"));section_id:Mapped[int]=mapped_column(ForeignKey("sections.id"));class_type:Mapped[str]=mapped_column(String(20),default="lecture",server_default="lecture");day_of_week:Mapped[int]=mapped_column(Integer);start_time:Mapped[time]=mapped_column(Time);end_time:Mapped[time]=mapped_column(Time);room_name:Mapped[str]=mapped_column(String(100));latitude:Mapped[float]=mapped_column(Float);longitude:Mapped[float]=mapped_column(Float);subject=relationship("Subject");section=relationship("Section")
class ScheduleOverride(Base):
    __tablename__ = "schedule_overrides"
    __table_args__ = (
        UniqueConstraint("timetable_entry_id", "override_date", name="uq_override_entry_date"),
        Index("ix_schedule_overrides_routine_entry_id", "routine_entry_id"),
        CheckConstraint(
            "routine_entry_id IS NOT NULL OR timetable_entry_id IS NOT NULL",
            name="ck_schedule_overrides_schedule_source",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_entry_id: Mapped[int | None] = mapped_column(ForeignKey("timetable_entries.id"), nullable=True)
    routine_entry_id: Mapped[int | None] = mapped_column(ForeignKey("routine_entries.id"), nullable=True)
    override_date: Mapped[date] = mapped_column(Date)
    new_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    new_room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_makeup: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[OverrideStatus] = mapped_column(Enum(OverrideStatus), default=OverrideStatus.PENDING)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timetable_entry = relationship("TimetableEntry")
    routine_entry = relationship("RoutineEntry")
    new_teacher = relationship("Teacher")
    new_room_reference = relationship("Room", foreign_keys=[new_room_id])
class ClassSession(Base):
    __tablename__="class_sessions";__table_args__=(Index("ix_class_sessions_routine_entry_id","routine_entry_id"),CheckConstraint("routine_entry_id IS NOT NULL OR timetable_entry_id IS NOT NULL",name="ck_class_sessions_schedule_source"),)
    id:Mapped[int]=mapped_column(primary_key=True);timetable_entry_id:Mapped[int|None]=mapped_column(ForeignKey("timetable_entries.id"),nullable=True);routine_entry_id:Mapped[int|None]=mapped_column(ForeignKey("routine_entries.id"),nullable=True);session_date:Mapped[date]=mapped_column(Date);effective_teacher_id:Mapped[int]=mapped_column(ForeignKey("teachers.id"));effective_room:Mapped[str]=mapped_column(String(100));schedule_override_id:Mapped[int|None]=mapped_column(ForeignKey("schedule_overrides.id"),nullable=True);status:Mapped[SessionStatus]=mapped_column(Enum(SessionStatus),default=SessionStatus.ACTIVE);started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());finalized_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);geofence_latitude:Mapped[float|None]=mapped_column(Float,nullable=True);geofence_longitude:Mapped[float|None]=mapped_column(Float,nullable=True);geofence_radius_meters:Mapped[float|None]=mapped_column(Float,nullable=True);teacher_location_accuracy_meters:Mapped[float|None]=mapped_column(Float,nullable=True);geofence_captured_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);self_checkin_window_minutes:Mapped[int|None]=mapped_column(Integer,nullable=True);challenge_rotation_seconds:Mapped[int|None]=mapped_column(Integer,nullable=True);current_qr_token:Mapped[str|None]=mapped_column(String(1000),nullable=True);qr_version:Mapped[int]=mapped_column(Integer,default=0,server_default="0");qr_nonce:Mapped[str|None]=mapped_column(String(64),nullable=True);qr_issued_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);qr_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True);timetable_entry=relationship("TimetableEntry");routine_entry=relationship("RoutineEntry");schedule_override=relationship("ScheduleOverride")
