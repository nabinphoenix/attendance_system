import enum
from datetime import date,time
from sqlalchemy import CheckConstraint, Date,Enum,ForeignKey,Integer,String,Time,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.core.database import Base
class SuggestionStatus(str,enum.Enum):PENDING="pending";APPROVED="approved";REJECTED="rejected"
class CoursePlan(Base):
    __tablename__ = "course_plans"
    __table_args__ = (
        UniqueConstraint("subject_id", "batch_id", name="uq_course_plan_subject_batch"),
        UniqueConstraint("module_offering_id", "batch_id", name="uq_course_plan_offering_batch"),
        CheckConstraint(
            "(subject_id IS NOT NULL) <> (module_offering_id IS NOT NULL)",
            name="ck_course_plan_source",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # subject_id is retained only for historical timetable records.
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    module_offering_id: Mapped[int | None] = mapped_column(ForeignKey("module_offerings.id"), nullable=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    planned_sessions: Mapped[int] = mapped_column(Integer)
    conducted_sessions: Mapped[int] = mapped_column(Integer, default=0)
    subject = relationship("Subject")
    module_offering = relationship("ModuleOffering")
    batch = relationship("Batch")
class MakeupSuggestion(Base):
    __tablename__ = "makeup_suggestions"
    __table_args__ = (
        CheckConstraint(
            "(timetable_entry_id IS NOT NULL) <> (routine_entry_id IS NOT NULL)",
            name="ck_makeup_suggestion_source",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    course_plan_id: Mapped[int] = mapped_column(ForeignKey("course_plans.id"))
    suggested_date: Mapped[date] = mapped_column(Date)
    suggested_start_time: Mapped[time] = mapped_column(Time)
    suggested_room: Mapped[str] = mapped_column(String(100))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    # timetable_entry_id is retained only for historical timetable records.
    timetable_entry_id: Mapped[int | None] = mapped_column(ForeignKey("timetable_entries.id"), nullable=True)
    routine_entry_id: Mapped[int | None] = mapped_column(ForeignKey("routine_entries.id"), nullable=True)
    status: Mapped[SuggestionStatus] = mapped_column(Enum(SuggestionStatus), default=SuggestionStatus.PENDING)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    timetable_entry = relationship("TimetableEntry")
    routine_entry = relationship("RoutineEntry")
