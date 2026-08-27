import enum
from datetime import date, datetime, time
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)

class Intake(Base):
    __tablename__ = "intakes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))

class Block(Base):
    __tablename__ = "blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("block_id", "name", name="uq_room_block_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id"))
    name: Mapped[str] = mapped_column(String(120))
    room_type: Mapped[str] = mapped_column(String(30))
    capacity: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    block = relationship("Block")

class AcademicModule(Base):
    __tablename__ = "modules"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int] = mapped_column(Integer)
    semester_number: Mapped[int] = mapped_column(Integer)


class ModuleOffering(Base):
    """A catalog module delivered to one intake, batch, and semester."""

    __tablename__ = "module_offerings"
    __table_args__ = (
        UniqueConstraint(
            "academic_module_id",
            "intake_id",
            "batch_id",
            "semester_number",
            name="uq_module_offering_context",
        ),
        Index("ix_module_offerings_academic_module_id", "academic_module_id"),
        Index("ix_module_offerings_intake_id", "intake_id"),
        Index("ix_module_offerings_batch_id", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    intake_id: Mapped[int] = mapped_column(ForeignKey("intakes.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    semester_number: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    academic_module: Mapped[AcademicModule] = relationship()
    intake: Mapped["Intake"] = relationship()
    batch: Mapped["Batch"] = relationship()
    sections: Mapped[list["Section"]] = relationship(
        secondary="module_offering_sections", back_populates="module_offerings"
    )
    routines: Mapped[list["RoutineEntry"]] = relationship(back_populates="module_offering")


def has_consistent_module_offering_context(offering: ModuleOffering) -> bool:
    """Return whether the loaded offering's intake and batch share a program."""

    return offering.intake.program_id == offering.batch.program_id

class ClassType(Base):
    __tablename__ = "class_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

class TimeSlot(Base):
    __tablename__ = "time_slots"
    __table_args__ = (UniqueConstraint("start_time", "end_time", name="uq_time_slot_range"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    duration_label: Mapped[str] = mapped_column(String(30))

class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))

class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    intake_id: Mapped[int | None] = mapped_column(ForeignKey("intakes.id"), nullable=True)
    semester_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    combined_with: Mapped[str | None] = mapped_column(String(100), nullable=True)
    module_offerings: Mapped[list[ModuleOffering]] = relationship(
        secondary="module_offering_sections", back_populates="sections"
    )

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    roll_number: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user = relationship("User")
    section = relationship("Section")
    subjects: Mapped[list["Subject"]] = relationship(secondary="student_subject_enrollments", back_populates="students")

class Guardian(Base):
    __tablename__ = "guardians"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True)
    user = relationship("User")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    students: Mapped[list[Student]] = relationship(secondary="student_subject_enrollments", back_populates="subjects")

class StudentSubjectEnrollment(Base):
    __tablename__ = "student_subject_enrollments"
    __table_args__ = (UniqueConstraint("student_id", "subject_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))

class RoutineEntry(Base):
    __tablename__ = "routine_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey("intakes.id"))
    semester_number: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    module_offering_id: Mapped[int | None] = mapped_column(ForeignKey("module_offerings.id"), nullable=True, index=True)
    class_type_id: Mapped[int] = mapped_column(ForeignKey("class_types.id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id"))
    intake = relationship("Intake")
    section = relationship("Section")
    module = relationship("AcademicModule")
    module_offering: Mapped[ModuleOffering | None] = relationship(back_populates="routines")
    class_type = relationship("ClassType")
    teacher = relationship("Teacher")
    room = relationship("Room")
    time_slot = relationship("TimeSlot")
    section_links: Mapped[list["RoutineEntrySection"]] = relationship(
        back_populates="routine_entry", cascade="all, delete-orphan"
    )
    pending_sections: Mapped[list["RoutinePendingSection"]] = relationship(
        back_populates="routine_entry", cascade="all, delete-orphan"
    )

class RoutineEntrySection(Base):
    """The sections attending one physical recurring class."""
    __tablename__ = "routine_entry_sections"
    __table_args__ = (UniqueConstraint("routine_entry_id", "section_id", name="uq_routine_entry_section"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_entry_id: Mapped[int] = mapped_column(ForeignKey("routine_entries.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    routine_entry: Mapped[RoutineEntry] = relationship(back_populates="section_links")
    section: Mapped[Section] = relationship()


class RoutinePendingSection(Base):
    """An intended combined-class membership whose section is not ready yet."""

    __tablename__ = "routine_pending_sections"
    __table_args__ = (
        UniqueConstraint("routine_entry_id", "section_name", name="uq_routine_pending_entry_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_entry_id: Mapped[int] = mapped_column(ForeignKey("routine_entries.id", ondelete="CASCADE"), index=True)
    section_name: Mapped[str] = mapped_column(String(50))
    intake_id: Mapped[int] = mapped_column(ForeignKey("intakes.id"))
    semester_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    routine_entry: Mapped[RoutineEntry] = relationship(back_populates="pending_sections")
    resolved_section: Mapped[Section | None] = relationship(foreign_keys=[resolved_section_id])


class ModuleOfferingSection(Base):
    __tablename__ = "module_offering_sections"
    __table_args__ = (
        UniqueConstraint("module_offering_id", "section_id", name="uq_module_offering_section"),
        Index("ix_module_offering_sections_section_id", "section_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    module_offering_id: Mapped[int] = mapped_column(ForeignKey("module_offerings.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))

class InvitationStatus(str, enum.Enum):
    SENT = "sent"
    ACTIVATED = "activated"
    REVOKED = "revoked"

class StudentInvitation(Base):
    __tablename__ = "student_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(Enum(InvitationStatus), default=InvitationStatus.SENT)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    student: Mapped[Student] = relationship()
