from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import DbSession, require_role, require_roles
from app.modules.identity.models import User

from .models import AcademicCalendar, CohortSemester, TeacherFeedback
from .semester_resource_schemas import (
    CalendarRead, FeedbackRead, FeedbackTeacherRead, FeedbackWrite, SemesterResourcesRead,
)
from .semester_resource_service import (
    MAX_CALENDAR_BYTES, can_read_semester, feedback_teachers, get_semester, today, validate_calendar,
)

router = APIRouter(prefix="/academic/semester-resources", tags=["semester-resources"])
Reader = Annotated[User, Depends(require_roles("admin", "teacher", "student"))]
Admin = Annotated[User, Depends(require_role("admin"))]
FeedbackReader = Annotated[User, Depends(require_roles("admin", "student"))]


def feedback_read(row, teacher, *, admin: bool):
    day = today()
    status = ("draft" if not row.is_published else "scheduled" if day < row.opens_on
              else "closed" if day > row.closes_on else "open")
    return FeedbackRead(
        id=row.id, cohort_semester_id=row.cohort_semester_id, teacher_id=row.teacher_id,
        teacher_name=teacher.user.name, title=row.title,
        form_url=row.form_url if admin or status == "open" else None,
        opens_on=row.opens_on, closes_on=row.closes_on, is_published=row.is_published, status=status,
    )


@router.get("/semesters", response_model=list[SemesterResourcesRead])
def list_semesters(actor: Reader, db: DbSession):
    calendars = {row.cohort_semester_id: row for row in db.scalars(select(AcademicCalendar)).all()}
    semesters = db.scalars(select(CohortSemester).order_by(CohortSemester.start_date.desc(), CohortSemester.id.desc())).all()
    return [
        SemesterResourcesRead(
            id=row.id, intake_name=row.intake.name, batch_name=row.batch.name,
            semester_number=row.semester_number, attempt_number=row.attempt_number,
            start_date=row.start_date, end_date=row.end_date,
            calendar=CalendarRead.model_validate(calendars[row.id]) if row.id in calendars else None,
        )
        for row in semesters if can_read_semester(db, actor, row)
    ]


@router.get("/semesters/{semester_id}/teachers", response_model=list[FeedbackTeacherRead])
def list_feedback_teachers(semester_id: int, actor: Admin, db: DbSession):
    semester = get_semester(db, actor, semester_id)
    return [FeedbackTeacherRead(id=t.id, name=t.user.name, employee_code=t.employee_code)
            for t in feedback_teachers(db, semester)]


@router.get("/semesters/{semester_id}/feedback", response_model=list[FeedbackRead])
def list_feedback(semester_id: int, actor: FeedbackReader, db: DbSession):
    semester = get_semester(db, actor, semester_id)
    admin = actor.role.value in {"admin", "super_admin"}
    teachers = {t.id: t for t in feedback_teachers(db, semester, actor)}
    query = select(TeacherFeedback).where(TeacherFeedback.cohort_semester_id == semester.id)
    if not admin:
        query = query.where(TeacherFeedback.is_published.is_(True))
    rows = db.scalars(query.order_by(TeacherFeedback.teacher_id)).all()
    # Admins can still maintain forms if the associated routine was removed.
    if admin:
        return [feedback_read(row, row.teacher, admin=True) for row in rows]
    return [feedback_read(row, teachers[row.teacher_id], admin=False)
            for row in rows if row.teacher_id in teachers]


@router.put("/semesters/{semester_id}/feedback/{teacher_id}", response_model=FeedbackRead)
def save_feedback(semester_id: int, teacher_id: int, payload: FeedbackWrite, actor: Admin, db: DbSession):
    semester = get_semester(db, actor, semester_id)
    if not semester.start_date <= payload.opens_on <= payload.closes_on <= semester.end_date:
        raise HTTPException(422, "Feedback dates must fall within the selected semester")
    row = db.scalar(select(TeacherFeedback).where(
        TeacherFeedback.cohort_semester_id == semester.id, TeacherFeedback.teacher_id == teacher_id,
    ))
    teacher = next((t for t in feedback_teachers(db, semester) if t.id == teacher_id), None)
    if teacher is None and row is None:
        raise HTTPException(422, "Choose a teacher assigned to this semester's routine")
    if row is None:
        row = TeacherFeedback(cohort_semester_id=semester.id, teacher_id=teacher_id, created_by=actor.id)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Feedback already exists for this teacher and semester. Reload and edit it.") from exc
    db.refresh(row)
    return feedback_read(row, row.teacher, admin=True)


@router.delete("/semesters/{semester_id}/feedback/{teacher_id}", status_code=204)
def delete_feedback(semester_id: int, teacher_id: int, actor: Admin, db: DbSession):
    get_semester(db, actor, semester_id)
    row = db.scalar(select(TeacherFeedback).where(
        TeacherFeedback.cohort_semester_id == semester_id, TeacherFeedback.teacher_id == teacher_id,
    ))
    if row is None:
        raise HTTPException(404, "Feedback form not found")
    db.delete(row)
    db.commit()


@router.put("/semesters/{semester_id}/calendar", response_model=CalendarRead)
def upload_calendar(semester_id: int, actor: Admin, db: DbSession, file: UploadFile = File(...)):
    get_semester(db, actor, semester_id)
    try:
        content = file.file.read(MAX_CALENDAR_BYTES + 1)
        filename = validate_calendar(file.filename, content)
    finally:
        file.file.close()
    row = db.scalar(select(AcademicCalendar).where(AcademicCalendar.cohort_semester_id == semester_id))
    if row is None:
        row = AcademicCalendar(cohort_semester_id=semester_id)
        db.add(row)
    row.filename, row.pdf_data, row.size_bytes = filename, content, len(content)
    row.uploaded_by, row.uploaded_at = actor.id, datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "The calendar changed during upload. Reload and try again.") from exc
    db.refresh(row)
    return row


@router.get("/semesters/{semester_id}/calendar")
def download_calendar(semester_id: int, actor: Reader, db: DbSession):
    get_semester(db, actor, semester_id)
    row = db.scalar(select(AcademicCalendar).where(AcademicCalendar.cohort_semester_id == semester_id))
    if row is None:
        raise HTTPException(404, "Academic calendar has not been uploaded")
    return Response(content=row.pdf_data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=academic-calendar.pdf; filename*=UTF-8''{quote(row.filename, safe='')}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.delete("/semesters/{semester_id}/calendar", status_code=204)
def delete_calendar(semester_id: int, actor: Admin, db: DbSession):
    get_semester(db, actor, semester_id)
    row = db.scalar(select(AcademicCalendar).where(AcademicCalendar.cohort_semester_id == semester_id))
    if row is None:
        raise HTTPException(404, "Academic calendar has not been uploaded")
    db.delete(row)
    db.commit()
