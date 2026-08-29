from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, Program, Room, Section, Student, Teacher, TimeSlot
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, SessionStatus
from app.modules.academic.models import RoutineEntry


def test_teacher_can_edit_past_and_today_attendance_by_date():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestSession() as db:
            program = Program(name="BCA")
            db.add(program)
            db.flush()
            intake = Intake(name="2026 Intake", code="I26", start_date=date(2026, 1, 1), program_id=program.id)
            batch = Batch(name="2026", program_id=program.id)
            db.add_all([intake, batch])
            db.flush()
            section = Section(name="A", batch_id=batch.id, intake_id=intake.id, semester_number=6)
            block = Block(name="Block A")
            module = AcademicModule(code="MAT", title="Mathematics", credits=3, semester_number=6)
            class_type = ClassType(name="Lecture")
            slot = TimeSlot(start_time=time(9), end_time=time(10), duration_label="1 hour")
            db.add_all([section, block, module, class_type, slot])
            db.flush()
            room = Room(block_id=block.id, name="A-101", room_type="lecture", capacity=40)
            teacher_user = User(name="Teacher", email="manual-teacher@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
            other_user = User(name="Other", email="other-teacher@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
            db.add_all([room, teacher_user, other_user])
            db.flush()
            teacher = Teacher(user_id=teacher_user.id, employee_code="MT1")
            other_teacher = Teacher(user_id=other_user.id, employee_code="MT2")
            db.add_all([teacher, other_teacher])
            db.flush()
            students = []
            for index in range(2):
                student_user = User(name=f"Student {index}", email=f"manual-student{index}@example.com", password_hash="x", role=UserRole.STUDENT)
                db.add(student_user)
                db.flush()
                student = Student(user_id=student_user.id, section_id=section.id, roll_number=f"M-{index}")
                db.add(student)
                students.append(student)
            db.flush()
            routine = RoutineEntry(
                intake_id=intake.id,
                semester_number=6,
                section_id=section.id,
                module_id=module.id,
                class_type_id=class_type.id,
                teacher_id=teacher.id,
                room_id=room.id,
                day_of_week=date.today().weekday(),
                time_slot_id=slot.id,
            )
            db.add(routine)
            db.commit()
            routine_id = routine.id
            student_id = students[0].id
            second_student_id = students[1].id

        client = TestClient(app)

        def auth(email):
            token = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        teacher_headers = auth("manual-teacher@example.com")
        other_headers = auth("other-teacher@example.com")
        past = (date.today() - timedelta(days=7)).isoformat()
        today = date.today().isoformat()

        available = client.get(f"/api/v1/teacher/attendance?date={past}", headers=teacher_headers)
        assert available.status_code == 200, available.text
        assert available.json()[0]["students"][0]["status"] == "not_checked_in"

        changed = client.put(
            f"/api/v1/teacher/attendance/{routine_id}/{student_id}?date={past}",
            headers=teacher_headers,
            json={"status": "present", "reason": "Paper attendance register"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["status"] == "present"

        with TestSession() as db:
            session = db.scalar(select(ClassSession).where(ClassSession.routine_entry_id == routine_id, ClassSession.session_date == date.fromisoformat(past)))
            assert session and session.status == SessionStatus.COMPLETED
            records = db.scalars(select(AttendanceRecord).where(AttendanceRecord.class_session_id == session.id).order_by(AttendanceRecord.student_id)).all()
            assert [record.status for record in records] == [AttendanceStatus.PRESENT, AttendanceStatus.ABSENT]

        today_change = client.put(
            f"/api/v1/teacher/attendance/{routine_id}/{second_student_id}?date={today}",
            headers=teacher_headers,
            json={"status": "absent", "reason": "Marked from classroom register"},
        )
        assert today_change.status_code == 200, today_change.text
        with TestSession() as db:
            session = db.scalar(select(ClassSession).where(ClassSession.routine_entry_id == routine_id, ClassSession.session_date == date.today()))
            assert session and session.status == SessionStatus.ACTIVE

        forbidden = client.put(
            f"/api/v1/teacher/attendance/{routine_id}/{student_id}?date={today}",
            headers=other_headers,
            json={"status": "present", "reason": "Should not be allowed"},
        )
        assert forbidden.status_code == 403, forbidden.text
        future = client.get(f"/api/v1/teacher/attendance?date={(date.today() + timedelta(days=1)).isoformat()}", headers=teacher_headers)
        assert future.status_code == 422, future.text
    finally:
        app.dependency_overrides.clear()
