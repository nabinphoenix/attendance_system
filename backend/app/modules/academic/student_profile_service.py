from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.academic.models import Student
from app.modules.identity.models import User, UserRole
from app.modules.operations.service import log_audit


def current_student_profile(db: Session, user: User) -> Student:
    """Return the account's student profile, repairing one safe legacy match."""
    if user.role != UserRole.STUDENT:
        raise HTTPException(403, "Only student accounts can access student records")

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student:
        return student

    # Legacy accounts can be linked only through one exact email match. Never
    # infer a student's section from their name.
    matches = db.scalars(
        select(Student).where(
            Student.user_id.is_(None),
            func.lower(Student.email) == user.email.strip().lower(),
        )
    ).all()
    if len(matches) == 1:
        student = matches[0]
        student.user_id = user.id
        log_audit(db, user.id, "student.profile_linked", "student", student.id, None, {"source": "exact_email_match"})
        db.commit()
        db.refresh(student)
        return student
    if len(matches) > 1:
        raise HTTPException(409, "Your account matches multiple student profiles. Ask an administrator to link it to the correct section.")
    raise HTTPException(404, "Your account is not linked to a student profile and section. Ask an administrator to link it before viewing student records.")
