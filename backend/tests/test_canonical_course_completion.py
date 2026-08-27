from datetime import date, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import (
    AcademicModule,
    Batch,
    Block,
    ClassType,
    Intake,
    ModuleOffering,
    ModuleOfferingSection,
    Program,
    Room,
    RoutineEntry,
    RoutineEntrySection,
    Section,
    Student,
    Teacher,
    TimeSlot,
)
from app.modules.attendance.models import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.modules.course_completion.models import CoursePlan
from app.modules.crm.models import StudentCase
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, ScheduleOverride, SessionStatus


def token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"}).json()["access_token"]


def canonical_environment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with Session() as db:
        program = Program(name="BCA")
        db.add(program)
        db.flush()
        batch = Batch(name="2026", program_id=program.id)
        db.add(batch)
        intake = Intake(name="January 2026", code="JAN26", start_date=date(2026, 1, 1), program_id=program.id)
        db.add(intake)
        db.flush()
        section = Section(name="A", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        block = Block(name="Block A")
        class_type = ClassType(name="Lecture")
        slot = TimeSlot(start_time=time(9), end_time=time(10), duration_label="1 hour")
        module = AcademicModule(code="IT601", title="Canonical Systems", credits=3, semester_number=6)
        db.add_all([section, block, class_type, slot, module])
        db.flush()
        room = Room(block_id=block.id, name="R1", room_type="classroom", capacity=40)
        admin = User(name="Admin", email="canonical.admin@example.com", password_hash=hash_password("Password123!"), role=UserRole.ADMIN)
        teacher_user = User(name="Teacher", email="canonical.teacher@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
        student_user = User(name="Student", email="canonical.student@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
        db.add_all([room, admin, teacher_user, student_user])
        db.flush()
        teacher = Teacher(user_id=teacher_user.id, employee_code="CAN-1")
        db.add(teacher)
        db.flush()
        student = Student(user_id=student_user.id, section_id=section.id, roll_number="CAN-1")
        offering = ModuleOffering(academic_module_id=module.id, intake_id=intake.id, batch_id=batch.id, semester_number=6)
        db.add_all([student, offering])
        db.flush()
        db.add(ModuleOfferingSection(module_offering_id=offering.id, section_id=section.id))
        routine = RoutineEntry(
            intake_id=intake.id,
            semester_number=6,
            section_id=section.id,
            module_id=module.id,
            module_offering_id=offering.id,
            class_type_id=class_type.id,
            teacher_id=teacher.id,
            room_id=room.id,
            day_of_week=date.today().weekday(),
            time_slot_id=slot.id,
        )
        db.add(routine)
        db.flush()
        db.add(RoutineEntrySection(routine_entry_id=routine.id, section_id=section.id))
        plan = CoursePlan(module_offering_id=offering.id, batch_id=batch.id, planned_sessions=5)
        db.add(plan)
        db.flush()
        for offset, status in enumerate([AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.ABSENT, AttendanceStatus.BUNK], start=1):
            session = ClassSession(
                routine_entry_id=routine.id,
                session_date=date.today() - timedelta(days=offset),
                effective_teacher_id=teacher.id,
                effective_room="R1",
                status=SessionStatus.COMPLETED,
            )
            db.add(session)
            db.flush()
            db.add(AttendanceRecord(class_session_id=session.id, student_id=student.id, status=status, method=AttendanceMethod.FINALIZATION))
        active = ClassSession(
            routine_entry_id=routine.id,
            session_date=date.today(),
            effective_teacher_id=teacher.id,
            effective_room="R1",
            status=SessionStatus.ACTIVE,
        )
        db.add(active)
        db.commit()
        return Session, {"plan": plan.id, "session": active.id, "student": student.id}


def test_canonical_attendance_drives_risk_completion_and_makeup():
    Session, ids = canonical_environment()
    client = TestClient(app)
    admin_headers = {"Authorization": f"Bearer {token(client, 'canonical.admin@example.com')}"}
    teacher_headers = {"Authorization": f"Bearer {token(client, 'canonical.teacher@example.com')}"}

    risk = client.post("/api/v1/analytics/risk-evaluations/run", headers=admin_headers)
    assert risk.status_code == 200 and risk.json()["created"] == 1
    with Session() as db:
        case = db.scalar(select(StudentCase))
        assert case.scope_type == "MODULE"
        assert case.scope_id is not None

    finalized = client.post(f"/api/v1/sessions/{ids['session']}/finalize", headers=teacher_headers)
    assert finalized.status_code == 200
    with Session() as db:
        assert db.get(CoursePlan, ids["plan"]).conducted_sessions == 1

    suggestion = client.post(f"/api/v1/course-completion/plans/{ids['plan']}/suggest-makeup", headers=admin_headers)
    assert suggestion.status_code == 200, suggestion.text
    approved = client.patch(
        f"/api/v1/course-completion/suggestions/{suggestion.json()['id']}",
        headers=admin_headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    with Session() as db:
        override = db.scalar(select(ScheduleOverride).where(ScheduleOverride.is_makeup.is_(True)))
        assert override and override.routine_entry_id is not None
    app.dependency_overrides.clear()
