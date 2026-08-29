from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, Program, Room, RoutineEntry, Section, Student, Teacher, TimeSlot
from app.modules.attendance.models import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, SessionStatus


def test_teacher_attendance_analysis_is_limited_to_assigned_sections_and_classes():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with Session() as db:
            program = Program(name="BCA")
            db.add(program)
            db.flush()
            intake = Intake(name="September 2026", code="SEP26", start_date=date(2026, 9, 1), program_id=program.id)
            batch = Batch(name="2026", program_id=program.id)
            db.add_all([intake, batch])
            db.flush()
            section = Section(name="A1", batch_id=batch.id, intake_id=intake.id, semester_number=6)
            other_section = Section(name="A2", batch_id=batch.id, intake_id=intake.id, semester_number=6)
            block = Block(name="Block B")
            module = AcademicModule(code="CT004", title="Advanced Database Systems", credits=3, semester_number=6)
            lecture = ClassType(name="Lecture")
            practical = ClassType(name="Practical")
            first_slot = TimeSlot(start_time=time(8), end_time=time(9), duration_label="1 hour")
            second_slot = TimeSlot(start_time=time(9), end_time=time(10), duration_label="1 hour")
            db.add_all([section, other_section, block, module, lecture, practical, first_slot, second_slot])
            db.flush()
            room = Room(block_id=block.id, name="L04", room_type="lecture", capacity=40)
            teacher_user = User(name="Teacher", email="analysis-teacher@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
            other_teacher_user = User(name="Other teacher", email="analysis-other@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
            db.add_all([room, teacher_user, other_teacher_user])
            db.flush()
            teacher = Teacher(user_id=teacher_user.id, employee_code="T-ANALYSIS")
            other_teacher = Teacher(user_id=other_teacher_user.id, employee_code="T-OTHER")
            db.add_all([teacher, other_teacher])
            db.flush()
            students = []
            for name, roll in (("Regular student", "A1-001"), ("At risk student", "A1-002")):
                user = User(name=name, email=f"{roll.lower()}@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
                db.add(user)
                db.flush()
                student = Student(user_id=user.id, section_id=section.id, roll_number=roll)
                db.add(student)
                students.append(student)
            db.flush()
            lecture_routine = RoutineEntry(intake_id=intake.id, semester_number=6, section_id=section.id, module_id=module.id, class_type_id=lecture.id, teacher_id=teacher.id, room_id=room.id, day_of_week=0, time_slot_id=first_slot.id)
            practical_routine = RoutineEntry(intake_id=intake.id, semester_number=6, section_id=section.id, module_id=module.id, class_type_id=practical.id, teacher_id=teacher.id, room_id=room.id, day_of_week=1, time_slot_id=second_slot.id)
            db.add_all([lecture_routine, practical_routine])
            db.flush()

            # The first student is regular (75%); the second needs attention (25%).
            status_pairs = [
                (lecture_routine, (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT)),
                (practical_routine, (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT)),
                (lecture_routine, (AttendanceStatus.PRESENT, AttendanceStatus.PRESENT)),
                (practical_routine, (AttendanceStatus.ABSENT, AttendanceStatus.ABSENT)),
            ]
            for offset, (routine, statuses) in enumerate(status_pairs):
                session = ClassSession(
                    routine_entry_id=routine.id,
                    session_date=date.today() - timedelta(days=offset + 1),
                    effective_teacher_id=teacher.id,
                    effective_room="Block B / L04",
                    status=SessionStatus.COMPLETED,
                )
                db.add(session)
                db.flush()
                for student, status in zip(students, statuses, strict=True):
                    db.add(AttendanceRecord(class_session_id=session.id, student_id=student.id, status=status, method=AttendanceMethod.FINALIZATION))
            db.commit()
            ids = {"module": module.id, "section": section.id, "lecture": lecture.id, "practical": practical.id}

        client = TestClient(app)

        def headers(email: str):
            token = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/analytics/teacher-attendance-analysis", headers=headers("analysis-teacher@example.com"))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 8
        assert payload["present"] == 4
        assert payload["overall_percentage"] == 50
        assert payload["scopes"] == [{
            "module_id": ids["module"], "module_name": "Advanced Database Systems", "module_code": "CT004",
            "section_id": ids["section"], "section_name": "A1",
        }]
        assert {item["class_type_name"]: item["percentage"] for item in payload["class_types"]} == {"Lecture": 75, "Practical": 25}
        assert [(item["student_name"], item["attendance_status"], item["percentage"]) for item in payload["students"]] == [
            ("At risk student", "needs_attention", 25),
            ("Regular student", "regular", 75),
        ]

        filtered = client.get(
            f"/api/v1/analytics/teacher-attendance-analysis?module_id={ids['module']}&section_id={ids['section']}&class_type_id={ids['practical']}",
            headers=headers("analysis-teacher@example.com"),
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 4
        assert filtered.json()["absent"] == 3

        forbidden = client.get(
            f"/api/v1/analytics/teacher-attendance-analysis?module_id={ids['module']}",
            headers=headers("analysis-other@example.com"),
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
