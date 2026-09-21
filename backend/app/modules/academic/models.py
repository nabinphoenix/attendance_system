import enum
from datetime import date, datetime, time
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, LargeBinary, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.tenancy import CollegeOwned

class Program(CollegeOwned, Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))

class Intake(CollegeOwned, Base):
    __tablename__ = "intakes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[date] = mapped_column(Date)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))

class CohortSemester(CollegeOwned, Base):
    __tablename__ = 'cohort_semesters'
    __table_args__ = (
        UniqueConstraint(
            'intake_id',
            'batch_id',
            'semester_number',
            'attempt_number',
            name='uq_cohort_semester_context',
        ),
        CheckConstraint('start_date <= end_date', name='ck_cohort_semester_dates'),
        Index('ix_cohort_semesters_context', 'intake_id', 'batch_id', 'semester_number'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey('intakes.id'))
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'))
    semester_number: Mapped[int] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default='planned', server_default='planned')
    intake: Mapped['Intake'] = relationship()
    batch: Mapped['Batch'] = relationship()

class Block(CollegeOwned, Base):
    __tablename__ = "blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

class Room(CollegeOwned, Base):
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

class AcademicModule(CollegeOwned, Base):
    __tablename__ = "modules"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int] = mapped_column(Integer)
    semester_number: Mapped[int] = mapped_column(Integer)


class ModuleOffering(CollegeOwned, Base):
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
    cohort_semester_id: Mapped[int | None] = mapped_column(
        ForeignKey('cohort_semesters.id'), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    academic_module: Mapped[AcademicModule] = relationship()
    intake: Mapped["Intake"] = relationship()
    batch: Mapped["Batch"] = relationship()
    sections: Mapped[list["Section"]] = relationship(
        secondary="module_offering_sections", back_populates="module_offerings"
    )
    routines: Mapped[list["RoutineEntry"]] = relationship(back_populates="module_offering")
    cohort_semester: Mapped[CohortSemester | None] = relationship()


def has_consistent_module_offering_context(offering: ModuleOffering) -> bool:
    """Return whether the loaded offering's intake and batch share a program."""

    return offering.intake.program_id == offering.batch.program_id

class ClassType(CollegeOwned, Base):
    __tablename__ = "class_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))

class TimeSlot(CollegeOwned, Base):
    __tablename__ = "time_slots"
    __table_args__ = (UniqueConstraint("college_id", "start_time", "end_time", name="uq_time_slot_range"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    duration_label: Mapped[str] = mapped_column(String(30))

class Batch(CollegeOwned, Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))

class Section(CollegeOwned, Base):
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

class Student(CollegeOwned, Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    roll_number: Mapped[str] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    enrollments: Mapped[list['StudentEnrollment']] = relationship(
        back_populates='student', cascade='all, delete-orphan'
    )
    user = relationship("User")
    section = relationship("Section")
    subjects: Mapped[list["Subject"]] = relationship(secondary="student_subject_enrollments", back_populates="students")

class PromotionRun(CollegeOwned, Base):
    '''One auditable transition from a source cohort semester to its successor.'''

    __tablename__ = 'promotion_runs'
    __table_args__ = (
        UniqueConstraint(
            'intake_id',
            'batch_id',
            'from_cohort_semester_id',
            'to_cohort_semester_id',
            'effective_date',
            name='uq_promotion_run_transition',
        ),
        Index('ix_promotion_runs_context', 'intake_id', 'batch_id', 'effective_date'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey('intakes.id'))
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'))
    from_cohort_semester_id: Mapped[int] = mapped_column(ForeignKey('cohort_semesters.id'))
    to_cohort_semester_id: Mapped[int] = mapped_column(ForeignKey('cohort_semesters.id'))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default='applied', server_default='applied')
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    items: Mapped[list['PromotionRunItem']] = relationship(
        back_populates='promotion_run', cascade='all, delete-orphan'
    )


class StudentEnrollment(CollegeOwned, Base):
    '''Dated student placement; historical rows are never overwritten.'''

    __tablename__ = 'student_enrollments'
    __table_args__ = (
        CheckConstraint('ends_on IS NULL OR starts_on < ends_on', name='ck_student_enrollment_dates'),
        Index('ix_student_enrollments_student_dates', 'student_id', 'starts_on', 'ends_on'),
        Index('ix_student_enrollments_section_dates', 'section_id', 'starts_on', 'ends_on'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'))
    section_id: Mapped[int] = mapped_column(ForeignKey('sections.id'))
    cohort_semester_id: Mapped[int | None] = mapped_column(
        ForeignKey('cohort_semesters.id'), nullable=True, index=True
    )
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='active', server_default='active')
    promotion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey('promotion_runs.id'), nullable=True, index=True
    )
    student: Mapped['Student'] = relationship(back_populates='enrollments')
    section: Mapped['Section'] = relationship()
    cohort_semester: Mapped[CohortSemester | None] = relationship()


class PromotionRunItem(CollegeOwned, Base):
    '''Per-student decision made by a promotion run.'''

    __tablename__ = 'promotion_run_items'
    __table_args__ = (
        UniqueConstraint('promotion_run_id', 'student_id', name='uq_promotion_run_item_student'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    promotion_run_id: Mapped[int] = mapped_column(
        ForeignKey('promotion_runs.id', ondelete='CASCADE')
    )
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'))
    source_enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey('student_enrollments.id'), nullable=True
    )
    target_enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey('student_enrollments.id'), nullable=True
    )
    source_section_id: Mapped[int] = mapped_column(ForeignKey('sections.id'))
    target_section_id: Mapped[int | None] = mapped_column(ForeignKey('sections.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promotion_run: Mapped[PromotionRun] = relationship(back_populates='items')


class Guardian(CollegeOwned, Base):
    __tablename__ = "guardians"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

class Teacher(CollegeOwned, Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(50))
    user = relationship("User")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    section = relationship("Section")
    students: Mapped[list[Student]] = relationship(secondary="student_subject_enrollments", back_populates="subjects")

class StudentSubjectEnrollment(CollegeOwned, Base):
    __tablename__ = "student_subject_enrollments"
    __table_args__ = (UniqueConstraint("student_id", "subject_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))

class RoutineEntry(CollegeOwned, Base):
    __tablename__ = "routine_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey("intakes.id"))
    semester_number: Mapped[int] = mapped_column(Integer)
    cohort_semester_id: Mapped[int | None] = mapped_column(
        ForeignKey('cohort_semesters.id'), nullable=True, index=True
    )
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

    cohort_semester: Mapped[CohortSemester | None] = relationship()


class RoutineEntrySection(CollegeOwned, Base):
    """The sections attending one physical recurring class."""
    __tablename__ = "routine_entry_sections"
    __table_args__ = (UniqueConstraint("routine_entry_id", "section_id", name="uq_routine_entry_section"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_entry_id: Mapped[int] = mapped_column(ForeignKey("routine_entries.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    routine_entry: Mapped[RoutineEntry] = relationship(back_populates="section_links")
    section: Mapped[Section] = relationship()


class RoutinePendingSection(CollegeOwned, Base):
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


class ModuleOfferingSection(CollegeOwned, Base):
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

class InvitationPurpose(str, enum.Enum):
    ACTIVATION = "activation"
    PASSWORD_SETUP = "password_setup"

class StudentInvitation(CollegeOwned, Base):
    __tablename__ = "student_invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(Enum(InvitationStatus), default=InvitationStatus.SENT)
    purpose: Mapped[InvitationPurpose] = mapped_column(
        Enum(InvitationPurpose), default=InvitationPurpose.ACTIVATION
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    student: Mapped[Student] = relationship()

# Different colleges may use the same catalog codes and local identifiers.
for _model, _column in ((Program, "name"), (Intake, "name"), (Intake, "code"), (Block, "name"), (AcademicModule, "code"), (ClassType, "name"), (Student, "roll_number"), (Teacher, "employee_code")):
    _model.__table__.append_constraint(UniqueConstraint("college_id", _column, name=f"uq_{_model.__tablename__}_college_{_column}"))

class AcademicCalendar(CollegeOwned, Base):
    __tablename__ = "academic_calendars"
    __table_args__ = (
        UniqueConstraint("cohort_semester_id", name="uq_academic_calendar_semester"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_calendar_size"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_semester_id: Mapped[int] = mapped_column(ForeignKey("cohort_semesters.id"))
    filename: Mapped[str] = mapped_column(String(255))
    pdf_data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeacherFeedback(CollegeOwned, Base):
    __tablename__ = "teacher_feedback"
    __table_args__ = (
        UniqueConstraint("cohort_semester_id", "teacher_id", name="uq_teacher_feedback_semester"),
        CheckConstraint("opens_on <= closes_on", name="ck_teacher_feedback_dates"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_semester_id: Mapped[int] = mapped_column(ForeignKey("cohort_semesters.id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    title: Mapped[str] = mapped_column(String(200))
    form_url: Mapped[str] = mapped_column(String(2048))
    opens_on: Mapped[date] = mapped_column(Date)
    closes_on: Mapped[date] = mapped_column(Date)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    teacher: Mapped[Teacher] = relationship()
