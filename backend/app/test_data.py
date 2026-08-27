"""Idempotently provision local test accounts for an existing academic setup.

This command deliberately leaves routines and existing records untouched.  It
creates any missing teacher accounts from the supplied timetable set and adds
student login accounts only until every configured section has the requested
number of students.
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.academic import models as academic_models  # Registers models.
from app.modules.academic.models import Section, Student, Teacher
from app.modules.identity.models import User, UserRole
from app.modules.operations import models as operations_models  # Registers models.
from app.modules.scheduling import models as scheduling_models  # Registers models.


DEFAULT_PASSWORD = "Welcome123!"
STUDENTS_PER_SECTION = 5
TEACHERS = (
    ("Daisy Napit", "daisy.napit@cps.edu.np", "FAC-DAISY"),
    ("Dipak Poudel", "dipak.poudel@cps.edu.np", "FAC-DIPAK"),
    ("Karan Shrestha", "karan.shrestha@cps.edu.np", "FAC-KARAN"),
    ("Nisha Gnawaly", "nisha.gnawaly@cps.edu.np", "FAC-NISHA"),
    ("Shuvit Shrestha", "shuvit.shrestha@cps.edu.np", "FAC-SHUVIT"),
)
STUDENTS_BY_SECTION = {
    "A1": (
        ("Aarav Sharma", "aarav.sharmasep26@cps.edu.np"),
        ("Sita Rai", "sita.raisep26@cps.edu.np"),
        ("Bikash Thapa", "bikash.thapasep26@cps.edu.np"),
        ("Nabin Pradhan", "nabin.pradhansep26@cps.edu.np"),
        ("Prisha Karki", "prisha.karkisep26@cps.edu.np"),
    ),
    "A2": (
        ("Aayush Dhakal", "aayush.dhakalsep26@cps.edu.np"),
        ("Prerana Rai", "prerana.raisep26@cps.edu.np"),
        ("Bibek Shrestha", "bibek.shresthasep26@cps.edu.np"),
        ("Sushma Gurung", "sushma.gurungsep26@cps.edu.np"),
        ("Ritesh Karki", "ritesh.karkisep26@cps.edu.np"),
    ),
    "A3": (
        ("Nabin Nepali", "nabin.nepalisep26@cps.edu.np"),
        ("Rojina Thapa", "rojina.thapasep26@cps.edu.np"),
        ("Sagar Bista", "sagar.bistasep26@cps.edu.np"),
        ("Alisha Tamang", "alisha.tamangsep26@cps.edu.np"),
    ),
    "A4": (
        ("Prakash Bhandari", "prakash.bhandarisep26@cps.edu.np"),
        ("Anju Poudel", "anju.poudelsep26@cps.edu.np"),
        ("Bishal Lama", "bishal.lamasep26@cps.edu.np"),
        ("Kritika Joshi", "kritika.joshisep26@cps.edu.np"),
        ("Sandesh Adhikari", "sandesh.adhikarisep26@cps.edu.np"),
    ),
}
def ensure_teacher(
    db, name: str, email: str, employee_code: str, *, reset_password: bool = False
) -> bool:
    """Create a teacher, or standardize a teacher found by employee code."""
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    teacher_by_code = db.scalar(select(Teacher).where(Teacher.employee_code == employee_code))

    if teacher_by_code is not None:
        if user is not None and user.id != teacher_by_code.user_id:
            raise ValueError(f"{email} already belongs to another account")
        account = teacher_by_code.user
        if account.role != UserRole.TEACHER:
            raise ValueError(f"{employee_code} does not belong to a teacher account")
        account.name = name
        account.email = email
        if reset_password:
            account.password_hash = hash_password(DEFAULT_PASSWORD)
        return False

    if user is not None:
        if user.role != UserRole.TEACHER:
            raise ValueError(f"{email} already belongs to a non-teacher account")
        teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        if teacher is None:
            if teacher_by_code is not None:
                raise ValueError(f"{employee_code} is already assigned to another teacher")
            db.add(Teacher(user_id=user.id, employee_code=employee_code))
            if reset_password:
                user.password_hash = hash_password(DEFAULT_PASSWORD)
            return True
        if teacher.employee_code != employee_code:
            raise ValueError(f"{email} already uses employee code {teacher.employee_code}")
        return False

    if teacher_by_code is not None:
        raise ValueError(f"{employee_code} is already assigned to another teacher")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(DEFAULT_PASSWORD),
        role=UserRole.TEACHER,
    )
    db.add(user)
    db.flush()
    db.add(Teacher(user_id=user.id, employee_code=employee_code))
    return True


def standardize_test_students(db) -> None:
    """Rename only records created by this command to the CPS email convention."""
    for section_name, students in STUDENTS_BY_SECTION.items():
        for index, (name, email) in enumerate(students, start=1):
            roll_number = f"TEST-{section_name}-{index:02d}"
            student = db.scalar(select(Student).where(Student.roll_number == roll_number))
            if student is None:
                continue
            if student.user is None:
                raise ValueError(f"{roll_number} has no linked student account")
            duplicate = db.scalar(
                select(User).where(
                    func.lower(User.email) == email.lower(), User.id != student.user_id
                )
            )
            if duplicate is not None:
                raise ValueError(f"{email} already belongs to another account")
            student.name = name
            student.email = email
            student.user.name = name
            student.user.email = email


def add_students_until_full(db, section: Section, target: int) -> int:
    """Give a section enough predictable student accounts to reach ``target``."""
    current = db.scalar(select(func.count(Student.id)).where(Student.section_id == section.id)) or 0
    created = 0
    for number, (name, email) in enumerate(STUDENTS_BY_SECTION.get(section.name, ()), start=1):
        if current + created >= target:
            break
        roll_number = f"TEST-{section.name.upper()}-{number:02d}"
        if db.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
            continue
        if db.scalar(select(Student.id).where(Student.roll_number == roll_number)):
            continue

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.flush()
        db.add(
            Student(
                user_id=user.id,
                section_id=section.id,
                roll_number=roll_number,
                name=name,
                email=email,
            )
        )
        created += 1
    return created


def run(*, reset_teacher_passwords: bool = False) -> None:
    with SessionLocal.begin() as db:
        created_teachers = sum(
            ensure_teacher(db, *teacher, reset_password=reset_teacher_passwords)
            for teacher in TEACHERS
        )
        standardize_test_students(db)
        created_students = {
            section.name: add_students_until_full(db, section, STUDENTS_PER_SECTION)
            for section in db.scalars(select(Section).order_by(Section.name)).all()
        }

    print(f"Teachers created: {created_teachers}; already present: {len(TEACHERS) - created_teachers}")
    if reset_teacher_passwords:
        print("Teacher passwords were reset to the test password.")
    print(f"Students created by section: {created_students}")
    print(f"Test password for newly created accounts: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset-teacher-passwords",
        action="store_true",
        help="reset the configured test teachers to the default test password",
    )
    run(reset_teacher_passwords=parser.parse_args().reset_teacher_passwords)
