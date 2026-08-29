"""Add report-ready demo data to an existing local AntimBench database.

The command is additive and idempotent: it never removes or changes existing
academic records.  It derives completed sessions from the configured routine,
so the normal analytics and export endpoints exercise real application data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.academic.models import (
    Guardian,
    ModuleOffering,
    RoutineEntry,
    RoutineEntrySection,
    Student,
)
from app.modules.analytics.service import run_risk_evaluations
from app.modules.attendance.models import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.modules.course_completion.models import CoursePlan, MakeupSuggestion
from app.modules.crm.models import CaseInteraction, CaseStatus, StudentCase
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import AuditLog
from app.modules.scheduling.models import ClassSession, ScheduleOverride, SessionStatus


DEMO_PASSWORD = "Demo123!"
DEMO_COORDINATOR_EMAIL = "demo.coordinator@antimbench.example.com"


def ensure_user(db, *, name: str, email: str, role: UserRole) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        if user.role != role:
            raise ValueError(f"{email} is already used by a {user.role.value} account")
        return user, False
    user = User(name=name, email=email, password_hash=hash_password(DEMO_PASSWORD), role=role)
    db.add(user)
    db.flush()
    return user, True


def historical_dates(day_of_week: int, *, sessions: int = 8) -> list[date]:
    """Return the most recent completed occurrences for a weekday (Monday=0)."""
    result: list[date] = []
    candidate = date.today() - timedelta(days=1)
    while len(result) < sessions:
        if candidate.weekday() == day_of_week:
            result.append(candidate)
        candidate -= timedelta(days=1)
    return list(reversed(result))


def attendance_status(student_id: int, routine_id: int, session_date: date) -> AttendanceStatus:
    """Give a stable mix of strong, borderline, and at-risk attendance."""
    score = (student_id * 17 + routine_id * 13 + session_date.toordinal() * 7) % 100
    if student_id % 11 == 0:
        passing_cutoff = 42  # Deliberately high-risk: creates support cases.
    elif student_id % 7 == 0:
        passing_cutoff = 62  # Borderline students demonstrate medium risk.
    else:
        passing_cutoff = 89

    if score < passing_cutoff:
        return AttendanceStatus.LATE if score % 13 == 0 else AttendanceStatus.PRESENT
    if score % 17 == 0:
        return AttendanceStatus.BUNK
    if score % 19 == 0:
        return AttendanceStatus.LEAVE
    return AttendanceStatus.ABSENT


def seed_sessions(db) -> tuple[int, int, list[Student], list[RoutineEntry]]:
    routines = db.scalars(select(RoutineEntry).order_by(RoutineEntry.id)).all()
    students = db.scalars(select(Student).order_by(Student.id)).all()
    roster_cache: dict[tuple[int, ...], list[Student]] = {}
    created_sessions = created_records = 0

    for routine in routines:
        section_ids = list(
            db.scalars(
                select(RoutineEntrySection.section_id).where(
                    RoutineEntrySection.routine_entry_id == routine.id
                )
            )
        ) or [routine.section_id]
        roster_key = tuple(sorted(section_ids))
        roster = roster_cache.setdefault(
            roster_key,
            db.scalars(select(Student).where(Student.section_id.in_(section_ids)).order_by(Student.id)).all(),
        )

        for session_date in historical_dates(routine.day_of_week):
            exists = db.scalar(
                select(ClassSession.id).where(
                    ClassSession.routine_entry_id == routine.id,
                    ClassSession.session_date == session_date,
                )
            )
            if exists is not None:
                continue

            started_at = datetime.combine(session_date, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            session = ClassSession(
                routine_entry_id=routine.id,
                session_date=session_date,
                effective_teacher_id=routine.teacher_id,
                effective_room=routine.room.name,
                status=SessionStatus.COMPLETED,
                started_at=started_at,
                finalized_at=started_at + timedelta(hours=1),
                geofence_latitude=routine.room.latitude,
                geofence_longitude=routine.room.longitude,
                geofence_radius_meters=routine.room.geofence_radius_meters,
            )
            db.add(session)
            db.flush()
            created_sessions += 1

            for student in roster:
                status = attendance_status(student.id, routine.id, session_date)
                db.add(
                    AttendanceRecord(
                        class_session_id=session.id,
                        student_id=student.id,
                        status=status,
                        method=AttendanceMethod.FINALIZATION,
                        check_in_time=(
                            started_at + timedelta(minutes=5 + student.id % 20)
                            if status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
                            else None
                        ),
                    )
                )
                created_records += 1
    return created_sessions, created_records, students, routines


def seed_support_data(db, students: list[Student], routines: list[RoutineEntry]) -> tuple[int, int]:
    admin = db.scalar(select(User).where(User.role == UserRole.ADMIN))
    if admin is None:
        admin, _ = ensure_user(
            db,
            name="Demo Administrator",
            email="admin@antimbench.example.com",
            role=UserRole.ADMIN,
        )
    coordinator, coordinator_created = ensure_user(
        db,
        name="Demo Coordinator",
        email=DEMO_COORDINATOR_EMAIL,
        role=UserRole.COORDINATOR,
    )

    guardians_created = 0
    at_risk_students = [student for student in students if student.id % 11 == 0 or student.id % 7 == 0]
    for student in at_risk_students[:3]:
        if db.scalar(select(Guardian.id).where(Guardian.student_id == student.id)) is not None:
            continue
        parent, _ = ensure_user(
            db,
            name=f"Demo Guardian {student.id}",
            email=f"demo.parent.{student.id}@antimbench.example.com",
            role=UserRole.PARENT,
        )
        db.add(Guardian(name=parent.name, student_id=student.id, user_id=parent.id, phone="9800000000"))
        guardians_created += 1

    routine = next((item for item in routines if item.module_offering_id is not None), None)
    if routine is not None:
        offering = db.get(ModuleOffering, routine.module_offering_id)
        plan = db.scalar(
            select(CoursePlan).where(
                CoursePlan.module_offering_id == offering.id,
                CoursePlan.batch_id == offering.batch_id,
            )
        )
        if plan is None:
            plan = CoursePlan(
                module_offering_id=offering.id,
                batch_id=offering.batch_id,
                planned_sessions=36,
                conducted_sessions=18,
            )
            db.add(plan)
            db.flush()
        if db.scalar(select(MakeupSuggestion.id).where(MakeupSuggestion.course_plan_id == plan.id)) is None:
            db.add(
                MakeupSuggestion(
                    course_plan_id=plan.id,
                    suggested_date=date.today() + timedelta(days=4),
                    suggested_start_time=routine.time_slot.start_time,
                    suggested_room=routine.room.name,
                    teacher_id=routine.teacher_id,
                    routine_entry_id=routine.id,
                )
            )
        override_date = date.today() + timedelta(days=7)
        if db.scalar(
            select(ScheduleOverride.id).where(
                ScheduleOverride.routine_entry_id == routine.id,
                ScheduleOverride.override_date == override_date,
            )
        ) is None:
            db.add(
                ScheduleOverride(
                    routine_entry_id=routine.id,
                    override_date=override_date,
                    reason="Demo pending room review",
                    created_by=admin.id,
                )
            )

    if db.scalar(select(AuditLog.id).where(AuditLog.action == "demo.analytics_seeded")) is None:
        db.add(
            AuditLog(
                actor_id=admin.id,
                action="demo.analytics_seeded",
                entity_type="demo_data",
                entity_id=admin.id,
                details="Added deterministic demo attendance and reporting data.",
            )
        )
    return int(coordinator_created), guardians_created


def assign_demo_cases() -> int:
    with SessionLocal.begin() as db:
        coordinator = db.scalar(select(User).where(User.email == DEMO_COORDINATOR_EMAIL))
        cases = db.scalars(
            select(StudentCase)
            .where(StudentCase.status == CaseStatus.OPEN)
            .order_by(StudentCase.id)
            .limit(5)
        ).all()
        for index, case in enumerate(cases):
            if case.assigned_to is None:
                case.assigned_to = coordinator.id
            if index == 0:
                case.status = CaseStatus.IN_PROGRESS
            if db.scalar(select(CaseInteraction.id).where(CaseInteraction.case_id == case.id)) is None:
                db.add(
                    CaseInteraction(
                        case_id=case.id,
                        staff_id=coordinator.id,
                        channel="phone",
                        notes="Demo follow-up scheduled after attendance review.",
                        outcome="Awaiting student support meeting.",
                    )
                )
    return len(cases)


def run() -> None:
    with SessionLocal.begin() as db:
        sessions, records, students, routines = seed_sessions(db)
        coordinator_created, guardians_created = seed_support_data(db, students, routines)

    with SessionLocal() as db:
        risk = run_risk_evaluations(db)
    assigned_cases = assign_demo_cases()

    print("Demo reporting data is ready (additive; no existing records were removed).")
    print(f"Created {sessions} completed sessions and {records} attendance records.")
    print(f"Created {coordinator_created} coordinator and {guardians_created} parent accounts.")
    print(f"Risk evaluation: {risk}; demo cases assigned: {assigned_cases}.")
    print(f"Demo coordinator login: {DEMO_COORDINATOR_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    run()
