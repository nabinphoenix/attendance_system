import io
from datetime import date, datetime, time

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, Section, Student, Teacher, TimeSlot
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, TimetableEntry


DAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
TEACHER_HEADER = ["intake_code", "semester", "sections", "day", "start_time", "end_time", "module_code", "class_type", "block", "room"]
SECTION_HEADER = ["day", "start_time", "end_time", "sections", "module_code", "module_title", "class_type", "lecturer_email", "block", "room"]


def xlsx_bytes(header, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Timetable"
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_canonical_teacher_and_section_import_workflow_csv_xlsx():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with Session() as db:
        program = Program(name="IT")
        db.add(program)
        db.flush()
        intake = Intake(name="September", code="NPT3F2509IT", start_date=date(2026, 9, 1), program_id=program.id)
        batch = Batch(name="2026", program_id=program.id)
        db.add_all([intake, batch])
        db.flush()
        sections = [Section(name=name, batch_id=batch.id, intake_id=intake.id, semester_number=6) for name in ("A1", "A2", "A3", "A4", "A5")]
        module = AcademicModule(code="CT004-3-3", title="Advanced Database Systems", credits=3, semester_number=6)
        block = Block(name="Block B")
        db.add_all([*sections, module, block])
        db.flush()
        offering = ModuleOffering(academic_module_id=module.id, intake_id=intake.id, batch_id=batch.id, semester_number=6, sections=sections[:4])
        room = Room(block_id=block.id, name="Machapuchare-L04", room_type="lecture", capacity=60)
        types = [ClassType(name=name) for name in ("Lecture", "Tutorial", "Practical")]
        slots = [TimeSlot(start_time=time(h, 0), end_time=time(h + 1, 0), duration_label="1h") for h in (8, 10, 12, 14, 16)]
        admin = User(name="Admin", email="admin@example.com", password_hash=hash_password("Password123!"), role=UserRole.ADMIN)
        teacher_user = User(name="Karan", email="karan@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
        student_users = [User(name=f"Student {name}", email=f"{name.lower()}@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT) for name in ("A1", "A2", "A3", "A4", "A5")]
        db.add_all([offering, room, *types, *slots, admin, teacher_user, *student_users])
        db.flush()
        teacher = Teacher(user_id=teacher_user.id, employee_code="T-KARAN")
        db.add(teacher)
        db.flush()
        db.add_all([Student(user_id=user.id, section_id=section.id, roll_number=f"R-{section.name}") for user, section in zip(student_users, sections)])
        db.commit()
        ids = {"teacher": teacher.id, "intake": intake.id, "offering": offering.id, **{section.name: section.id for section in sections}}

    client = TestClient(app)
    def auth(email):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    admin_headers = auth("admin@example.com")
    teacher_headers = auth("karan@example.com")
    catalog = client.get("/api/v1/academic/catalog", headers=teacher_headers)
    assert catalog.status_code == 200, catalog.text
    assert {"modules", "class-types", "rooms", "blocks", "time-slots", "intakes", "teachers"} <= set(catalog.json())
    today = datetime.now().weekday()
    teacher_rows = [
        ["NPT3F2509IT", "SEM VI", "A3|A4", DAY_CODES[today], "08:00", "09:00", "CT004-3-3", "Lecture", "Block B", "Machapuchare-L04"],
        ["NPT3F2509IT", "SEM VI", "A3", DAY_CODES[(today + 1) % 7], "10:00", "11:00", "CT004-3-3", "Tutorial", "Block B", "Machapuchare-L04"],
        ["NPT3F2509IT", "SEM VI", "A1|A2", DAY_CODES[(today + 2) % 7], "12:00", "13:00", "CT004-3-3", "Lecture", "Block B", "Machapuchare-L04"],
    ]
    teacher_csv = (",".join(TEACHER_HEADER) + "\n" + "\n".join(",".join(row) for row in teacher_rows) + "\n").encode()
    preview = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/preview", headers=admin_headers, files={"file": ("teacher.csv", io.BytesIO(teacher_csv), "text/csv")})
    assert preview.status_code == 200, preview.text
    assert (preview.json()["new_rows"], preview.json()["invalid_rows"]) == (3, 0)
    imported = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/import", headers=admin_headers, files={"file": ("teacher.csv", io.BytesIO(teacher_csv), "text/csv")})
    assert imported.status_code == 200 and imported.json()["success_count"] == 3, imported.text

    teacher_xlsx = xlsx_bytes(TEACHER_HEADER, teacher_rows)
    reimport = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/import", headers=admin_headers, files={"file": ("teacher.xlsx", io.BytesIO(teacher_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert reimport.status_code == 200 and reimport.json()["success_count"] == 3
    with Session() as db:
        routines = db.scalars(select(RoutineEntry)).all()
        assert len(routines) == 3
        assert {routine.module_offering_id for routine in routines} == {ids["offering"]}
        assert db.scalar(select(TimetableEntry)) is None

    legacy_header = ["intake_code", "semester_number", "section_name", "module_code", "class_type", "teacher_email", "block_name", "room_name", "day_of_week", "start_time", "end_time"]
    legacy_row = ["NPT3F2509IT", "6", "A3", "CT004-3-3", "Lecture", "karan@example.com", "Block B", "Machapuchare-L04", DAY_CODES[today], "08:00", "09:00"]
    legacy_csv = (",".join(legacy_header) + "\n" + ",".join(legacy_row) + "\n").encode()
    legacy_import = client.post("/api/v1/imports/routines", headers=admin_headers, files={"file": ("legacy-routine.csv", io.BytesIO(legacy_csv), "text/csv")})
    assert legacy_import.status_code == 200, legacy_import.text
    assert legacy_import.json()["success_count"] == 1
    assert legacy_import.json()["failed_count"] == 0
    with Session() as db:
        assert len(db.scalars(select(RoutineEntry)).all()) == 3

    teacher_view = client.get("/api/v1/academic/teachers/me/routines", headers=teacher_headers)
    assert teacher_view.status_code == 200 and len(teacher_view.json()) == 3
    paged = client.get("/api/v1/academic/routines/page?page=1&page_size=5", headers=admin_headers)
    assert paged.status_code == 200, paged.text
    assert paged.json()["total"] == 3 and len(paged.json()["items"]) == 3
    section_page = client.get(f"/api/v1/academic/routines/page?page=1&page_size=5&section_id={ids['A3']}", headers=admin_headers)
    assert section_page.status_code == 200 and section_page.json()["total"] == 2
    assert len(client.get(f"/api/v1/academic/routines?section_id={ids['A1']}", headers=admin_headers).json()) == 1
    assert len(client.get(f"/api/v1/academic/routines?section_id={ids['A2']}", headers=admin_headers).json()) == 1
    assert len(client.get(f"/api/v1/academic/routines?section_id={ids['A3']}", headers=admin_headers).json()) == 2
    assert len(client.get(f"/api/v1/academic/routines?section_id={ids['A4']}", headers=admin_headers).json()) == 1
    assert not client.get(f"/api/v1/academic/routines?section_id={ids['A5']}", headers=admin_headers).json()
    for name, expected in (("A1", 1), ("A2", 1), ("A3", 2), ("A4", 1), ("A5", 0)):
        response = client.get("/api/v1/academic/routines/me", headers=auth(f"{name.lower()}@example.com"))
        assert response.status_code == 200 and len(response.json()) == expected

    today_routine = next(row for row in teacher_view.json() if row["day_of_week"] == today)
    started = client.post(f"/api/v1/routine-sessions/{today_routine['id']}/start", headers=teacher_headers, json={"latitude": 27.7172, "longitude": 85.3240, "accuracy_meters": 12})
    assert started.status_code == 200, started.text
    with Session() as db:
        assert db.query(ClassSession).count() == 1

    section_rows = [[DAY_CODES[today], "08:00", "09:00", "A3|A4", "CT004-3-3", "Advanced Database Systems", "Lecture", "karan@example.com", "Block B", "Machapuchare-L04"]]
    section_csv = (",".join(SECTION_HEADER) + "\n" + ",".join(section_rows[0]) + "\n").encode()
    section_import = client.post(f"/api/v1/academic/sections/{ids['A3']}/routine/import?intake_id={ids['intake']}&semester_number=6", headers=admin_headers, files={"file": ("section.csv", io.BytesIO(section_csv), "text/csv")})
    assert section_import.status_code == 200 and section_import.json()["success_count"] == 1
    section_xlsx = xlsx_bytes(SECTION_HEADER, section_rows)
    section_reimport = client.post(f"/api/v1/academic/sections/{ids['A3']}/routine/import?intake_id={ids['intake']}&semester_number=6", headers=admin_headers, files={"file": ("section.xlsx", io.BytesIO(section_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert section_reimport.status_code == 200 and section_reimport.json()["success_count"] == 1

    combined_tutorial = [["NPT3F2509IT", "SEM VI", "A1|A2", DAY_CODES[(today + 3) % 7], "14:00", "15:00", "CT004-3-3", "Tutorial", "Block B", "Machapuchare-L04"]]
    tutorial_csv = (",".join(TEACHER_HEADER) + "\n" + ",".join(combined_tutorial[0]) + "\n").encode()
    tutorial_import = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/import", headers=admin_headers, files={"file": ("tutorial.csv", io.BytesIO(tutorial_csv), "text/csv")})
    assert tutorial_import.status_code == 200 and tutorial_import.json()["success_count"] == 1
    combined_practical = [["NPT3F2509IT", "SEM VI", "A3|A4", DAY_CODES[(today + 4) % 7], "16:00", "17:00", "CT004-3-3", "Practical", "Block B", "Machapuchare-L04"]]
    practical_import = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/import", headers=admin_headers, files={"file": ("practical.xlsx", io.BytesIO(xlsx_bytes(TEACHER_HEADER, combined_practical)), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert practical_import.status_code == 200 and practical_import.json()["success_count"] == 1

    with Session() as db:
        db.get(ModuleOffering, ids["offering"]).is_active = False
        db.commit()
    inactive_row = [["NPT3F2509IT", "SEM VI", "A1", DAY_CODES[(today + 5) % 7], "08:00", "09:00", "CT004-3-3", "Lecture", "Block B", "Machapuchare-L04"]]
    inactive_csv = (",".join(TEACHER_HEADER) + "\n" + ",".join(inactive_row[0]) + "\n").encode()
    inactive = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/preview", headers=admin_headers, files={"file": ("inactive.csv", io.BytesIO(inactive_csv), "text/csv")})
    assert inactive.json()["invalid_rows"] == 1
    assert "No active module offering" in inactive.json()["errors"][0]["error_message"]
    with Session() as db:
        db.get(ModuleOffering, ids["offering"]).is_active = True
        db.commit()
    invalid_row = [["NPT3F2509IT", "SEM VI", "A5", DAY_CODES[(today + 5) % 7], "14:00", "15:00", "CT004-3-3", "Tutorial", "Block B", "Machapuchare-L04"]]
    invalid_csv = (",".join(TEACHER_HEADER) + "\n" + ",".join(invalid_row[0]) + "\n").encode()
    invalid = client.post(f"/api/v1/academic/teachers/{ids['teacher']}/timetable/preview", headers=admin_headers, files={"file": ("invalid.csv", io.BytesIO(invalid_csv), "text/csv")})
    assert invalid.json()["invalid_rows"] == 1
    assert "not part of the active module offering" in invalid.json()["errors"][0]["error_message"]
    app.dependency_overrides.clear()
