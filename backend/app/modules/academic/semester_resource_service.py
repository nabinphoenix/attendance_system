from datetime import datetime
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import User

from .models import CohortSemester, RoutineEntry, Section, Student, StudentEnrollment, Teacher
from .promotion_service import student_enrollment_at
from .student_profile_service import current_student_profile

MAX_CALENDAR_BYTES = 10 * 1024 * 1024


def today():
    return datetime.now(ZoneInfo(settings.academic_timezone)).date()


def current_student_placement(db: Session, user: User):
    student = current_student_profile(db, user)
    enrollment = student_enrollment_at(db, student.id, today())
    if enrollment:
        return db.get(Section, enrollment.section_id), enrollment.cohort_semester_id
    # Legacy students have no dated placements. Do not revive an ended or
    # withdrawn enrollment using the student's cached section.
    if db.scalar(select(StudentEnrollment.id).where(StudentEnrollment.student_id == student.id).limit(1)):
        return None, None
    return db.get(Section, student.section_id), None


def routine_in_semester(semester: CohortSemester):
    # Legacy routines can be matched by their complete cohort context.
    return or_(
        RoutineEntry.cohort_semester_id == semester.id,
        and_(
            RoutineEntry.cohort_semester_id.is_(None),
            RoutineEntry.intake_id == semester.intake_id,
            RoutineEntry.semester_number == semester.semester_number,
            RoutineEntry.section.has(Section.batch_id == semester.batch_id),
        ),
    )


def section_in_semester(section: Section | None, semester: CohortSemester) -> bool:
    return bool(section and section.batch_id == semester.batch_id
                and section.intake_id == semester.intake_id
                and section.semester_number == semester.semester_number)


def student_is_current(db: Session, user: User, semester: CohortSemester) -> bool:
    section, cohort_id = current_student_placement(db, user)
    if cohort_id is not None:
        return cohort_id == semester.id
    return section_in_semester(section, semester) and semester.start_date <= today() <= semester.end_date


def can_read_semester(db: Session, user: User, semester: CohortSemester) -> bool:
    if user.role.value in {"admin", "super_admin"}:
        return True
    if user.role.value == "teacher":
        teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        return bool(teacher and db.scalar(select(RoutineEntry.id).where(
            RoutineEntry.teacher_id == teacher.id, routine_in_semester(semester)
        ).limit(1)))
    if user.role.value == "student":
        if student_is_current(db, user, semester):
            return True
        return db.scalar(select(StudentEnrollment.id).join(Student).where(
            Student.user_id == user.id,
            StudentEnrollment.cohort_semester_id == semester.id,
            StudentEnrollment.status != "withdrawn",
            StudentEnrollment.starts_on <= today(),
        ).limit(1)) is not None
    return False


def get_semester(db: Session, user: User, semester_id: int) -> CohortSemester:
    semester = db.get(CohortSemester, semester_id)
    if semester is None or not can_read_semester(db, user, semester):
        raise HTTPException(404, "Semester not found")
    return semester


def feedback_teachers(db: Session, semester: CohortSemester, user: User | None = None):
    query = select(Teacher).where(Teacher.id.in_(
        select(RoutineEntry.teacher_id).where(routine_in_semester(semester))
    ))
    if user and user.role.value == "student":
        if not student_is_current(db, user, semester):
            return []
        section, _ = current_student_placement(db, user)
        if section is None:
            return []
        from .models import RoutineEntrySection
        query = query.where(Teacher.id.in_(
            select(RoutineEntry.teacher_id).where(
                routine_in_semester(semester),
                or_(RoutineEntry.section_id == section.id,
                    RoutineEntry.section_links.any(RoutineEntrySection.section_id == section.id)),
            )
        ))
    return db.scalars(query.order_by(Teacher.employee_code)).all()


def validate_calendar(filename: str | None, content: bytes) -> str:
    if len(content) > MAX_CALENDAR_BYTES:
        raise HTTPException(413, "Academic calendar must be 10 MB or smaller")
    if not filename or not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Upload a valid PDF file")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) == 0:
            raise ValueError("Encrypted or empty PDF")
    except Exception as exc:
        raise HTTPException(422, "Upload a readable, unencrypted PDF with at least one page") from exc
    # Never use a client path as a server path or an unescaped response header.
    basename = filename.replace("\\", "/").split("/")[-1]
    return re.sub(r"[\x00-\x1f\x7f]", "", basename)[:240] or "academic-calendar.pdf"
