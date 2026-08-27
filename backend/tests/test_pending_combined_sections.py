import io
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, RoutineEntrySection, RoutinePendingSection, Section, Student, Teacher, TimeSlot
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import ImportJob


HEADER = "day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room\n"


def routine_csv(*, sections="A1|A2", day="MON", start="08:00", end="09:00", class_type="Lecture", room="Room 1"):
    return (HEADER + ",".join([day, start, end, sections, "CT004", "Advanced Database Systems", class_type, "karan@example.com", "Block B", room]) + "\n").encode()


def setup_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with Session() as db:
        admin = User(name="Admin", email="admin@example.com", password_hash=hash_password("Password123!"), role=UserRole.ADMIN)
        karan_user = User(name="Karan", email="karan@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
        bina_user = User(name="Bina", email="bina@example.com", password_hash=hash_password("Password123!"), role=UserRole.TEACHER)
        a1_user = User(name="A1 Student", email="a1.student@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
        program = Program(name="IT")
        batch = Batch(name="2026", program_id=1)
        intake = Intake(name="September", code="SEP", start_date=date(2026, 9, 1), program_id=1)
        db.add_all([admin, karan_user, bina_user, a1_user, program])
        db.flush()
        batch.program_id = program.id
        intake.program_id = program.id
        db.add_all([batch, intake])
        db.flush()
        a1 = Section(name="A1", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        module = AcademicModule(code="CT004", title="Advanced Database Systems", credits=3, semester_number=6)
        block = Block(name="Block B")
        db.add_all([a1, module, block])
        db.flush()
        rooms = {name: Room(block_id=block.id, name=name, room_type="lecture", capacity=60) for name in ("Room 1", "Room 2")}
        class_types = {name: ClassType(name=name) for name in ("Lecture", "Tutorial", "Practical")}
        slots = {
            "base": TimeSlot(start_time=time(8), end_time=time(9), duration_label="1h"),
            "second": TimeSlot(start_time=time(9), end_time=time(10), duration_label="1h"),
            "third": TimeSlot(start_time=time(10), end_time=time(11), duration_label="1h"),
        }
        db.add_all([*rooms.values(), *class_types.values(), *slots.values()])
        db.flush()
        karan = Teacher(user_id=karan_user.id, employee_code="T-KARAN")
        bina = Teacher(user_id=bina_user.id, employee_code="T-BINA")
        offering = ModuleOffering(academic_module_id=module.id, intake_id=intake.id, batch_id=batch.id, semester_number=6, sections=[a1])
        a1_student = Student(user_id=a1_user.id, section_id=a1.id, roll_number="A1-001")
        db.add_all([karan, bina, offering, a1_student])
        db.commit()
        return Session, {"admin": admin.id, "intake": intake.id, "batch": batch.id, "a1": a1.id, "module": module.id, "offering": offering.id, "block": block.id, "room1": rooms["Room 1"].id, "room2": rooms["Room 2"].id, "lecture": class_types["Lecture"].id, "tutorial": class_types["Tutorial"].id, "practical": class_types["Practical"].id, "slot": slots["base"].id, "karan": karan.id, "bina": bina.id}


def auth(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def section_endpoint(ids, section="a1"):
    return f"/api/v1/academic/sections/{ids[section]}/routine"


def context_query(ids):
    return f"?intake_id={ids['intake']}&semester_number=6"


def add_a2_and_offer(client, admin_headers, Session, ids, *, intake_id=None, semester=6):
    created = client.post("/api/v1/academic/sections", headers=admin_headers, json={"name": "A2", "batch_id": ids["batch"], "intake_id": intake_id or ids["intake"], "semester_number": semester})
    assert created.status_code == 200, created.text
    a2_id = created.json()["id"]
    if semester == 6 and (intake_id is None or intake_id == ids["intake"]):
        offering = client.get(f"/api/v1/academic/module-offerings/{ids['offering']}", headers=admin_headers)
        assert offering.status_code == 200 and set(offering.json()["section_ids"]) == {ids["a1"], a2_id}
    return a2_id


def test_pending_combined_section_lifecycle_and_projection():
    Session, ids = setup_context()
    client = TestClient(app)
    admin = auth(client, "admin@example.com")
    endpoint = section_endpoint(ids)
    try:
        preview = client.post(endpoint + "/preview" + context_query(ids), headers=admin, files={"file": ("routine.csv", io.BytesIO(routine_csv()), "text/csv")})
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert (body["total_rows"], body["new_rows"], body["pending_section_references"], body["invalid_rows"]) == (1, 1, 1, 0)
        assert body["rows"][0]["status"] == "valid_new_with_pending"
        with Session() as db:
            assert db.scalar(select(RoutineEntry)) is None
            assert db.scalar(select(RoutinePendingSection)) is None
            assert db.scalar(select(ImportJob)) is None

        imported = client.post(endpoint + "/import" + context_query(ids), headers=admin, files={"file": ("routine.csv", io.BytesIO(routine_csv()), "text/csv")})
        assert imported.status_code == 200, imported.text
        assert (imported.json()["success_count"], imported.json()["pending_section_references"]) == (1, 1)
        with Session() as db:
            entry = db.scalar(select(RoutineEntry))
            assert entry is not None
            assert {link.section_id for link in entry.section_links} == {ids["a1"]}
            pending = db.scalar(select(RoutinePendingSection))
            assert pending is not None and pending.section_name == "A2" and pending.resolved_section_id is None

        assert len(client.get("/api/v1/academic/teachers/me/routines", headers=auth(client, "karan@example.com")).json()) == 1
        assert len(client.get("/api/v1/academic/routines/me", headers=auth(client, "a1.student@example.com")).json()) == 1
        pending_api = client.get(endpoint.replace("/routine", "/routine/pending") + context_query(ids), headers=admin)
        assert pending_api.status_code == 200 and pending_api.json()[0]["section_name"] == "A2"

        # Exact re-import stays idempotent and does not create another pending row.
        repeat = client.post(endpoint + "/import" + context_query(ids), headers=admin, files={"file": ("routine.csv", io.BytesIO(routine_csv()), "text/csv")})
        assert repeat.status_code == 200 and repeat.json()["success_count"] == 1
        with Session() as db:
            assert len(db.scalars(select(RoutineEntry)).all()) == 1
            assert len(db.scalars(select(RoutinePendingSection).where(RoutinePendingSection.resolved_section_id.is_(None))).all()) == 1

        a2_id = add_a2_and_offer(client, admin, Session, ids)
        with Session() as db:
            a2_user = User(name="A2 Student", email="a2.student@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
            db.add(a2_user)
            db.flush()
            db.add(Student(user_id=a2_user.id, section_id=a2_id, roll_number="A2-001"))
            db.commit()

        # A2 can now import its own copy; identity matches the existing physical class.
        a2_endpoint = section_endpoint({**ids, "a2": a2_id}, "a2")
        a2_preview = client.post(a2_endpoint + "/preview" + context_query(ids), headers=admin, files={"file": ("a2.csv", io.BytesIO(routine_csv(sections="A2")), "text/csv")})
        assert a2_preview.status_code == 200 and a2_preview.json()["merge_rows"] == 1 and a2_preview.json()["pending_section_references"] == 0
        a2_import = client.post(a2_endpoint + "/import" + context_query(ids), headers=admin, files={"file": ("a2.csv", io.BytesIO(routine_csv(sections="A2")), "text/csv")})
        assert a2_import.status_code == 200 and a2_import.json()["success_count"] == 1
        with Session() as db:
            entries = db.scalars(select(RoutineEntry)).all()
            assert len(entries) == 1
            assert {link.section_id for link in entries[0].section_links} == {ids["a1"], a2_id}
            pending = db.scalar(select(RoutinePendingSection))
            assert pending.resolved_section_id == a2_id and pending.resolved_at is not None
        assert client.get(endpoint.replace("/routine", "/routine/pending") + context_query(ids), headers=admin).json() == []
        assert len(client.get("/api/v1/academic/routines/me", headers=auth(client, "a2.student@example.com")).json()) == 1
        assert len(client.get("/api/v1/academic/teachers/me/routines", headers=auth(client, "karan@example.com")).json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_pending_typo_multiple_sections_and_class_types_never_autocreate():
    Session, ids = setup_context()
    client = TestClient(app)
    admin = auth(client, "admin@example.com")
    endpoint = section_endpoint(ids)
    try:
        for class_type, day, start, end in (("Lecture", "MON", "08:00", "09:00"), ("Tutorial", "TUE", "09:00", "10:00"), ("Practical", "WED", "10:00", "11:00")):
            file = routine_csv(sections="A1|A2|A3", day=day, start=start, end=end, class_type=class_type)
            response = client.post(endpoint + "/preview" + context_query(ids), headers=admin, files={"file": ("routine.csv", io.BytesIO(file), "text/csv")})
            assert response.status_code == 200, response.text
            assert response.json()["invalid_rows"] == 0 and response.json()["pending_section_references"] == 2
        typo = client.post(endpoint + "/preview" + context_query(ids), headers=admin, files={"file": ("typo.csv", io.BytesIO(routine_csv(sections="A1|A21", day="THU", start="08:00", end="09:00")), "text/csv")})
        assert typo.status_code == 200 and typo.json()["invalid_rows"] == 0
        with Session() as db:
            assert db.scalar(select(Section).where(Section.name == "A21")) is None
    finally:
        app.dependency_overrides.clear()


def test_later_resolution_conflict_is_blocked_after_section_inherits_offering():
    Session, ids = setup_context()
    client = TestClient(app)
    admin = auth(client, "admin@example.com")
    endpoint = section_endpoint(ids)
    try:
        imported = client.post(endpoint + "/import" + context_query(ids), headers=admin, files={"file": ("routine.csv", io.BytesIO(routine_csv()), "text/csv")})
        assert imported.status_code == 200
        a2 = client.post("/api/v1/academic/sections", headers=admin, json={"name": "A2", "batch_id": ids["batch"], "intake_id": ids["intake"], "semester_number": 6}).json()
        a2_id = a2["id"]
        a2_endpoint = f"/api/v1/academic/sections/{a2_id}/routine"
        offering = client.get(f"/api/v1/academic/module-offerings/{ids['offering']}", headers=admin)
        assert offering.status_code == 200 and set(offering.json()["section_ids"]) == {ids["a1"], a2_id}
        with Session() as db:
            conflict = RoutineEntry(intake_id=ids["intake"], semester_number=6, section_id=a2_id, module_id=ids["module"], class_type_id=ids["tutorial"], teacher_id=ids["bina"], room_id=ids["room2"], day_of_week=0, time_slot_id=ids["slot"])
            db.add(conflict)
            db.flush()
            db.add(RoutineEntrySection(routine_entry_id=conflict.id, section_id=a2_id))
            db.commit()
        resolution = client.post(a2_endpoint + "/preview" + context_query(ids), headers=admin, files={"file": ("a2.csv", io.BytesIO(routine_csv(sections="A2")), "text/csv")})
        assert resolution.status_code == 200 and resolution.json()["invalid_rows"] == 1
        assert "Section conflict" in resolution.json()["errors"][0]["error_message"]
        with Session() as db:
            pending = db.scalar(select(RoutinePendingSection).where(RoutinePendingSection.section_name == "A2"))
            assert pending.resolved_section_id is None
    finally:
        app.dependency_overrides.clear()


def test_wrong_context_section_cannot_be_selected_for_resolution():
    Session, ids = setup_context()
    client = TestClient(app)
    admin = auth(client, "admin@example.com")
    try:
        other_intake = client.post("/api/v1/academic/intakes", headers=admin, json={"name": "January", "code": "JAN", "start_date": "2027-01-01", "program_id": 1}).json()
        wrong = client.post("/api/v1/academic/sections", headers=admin, json={"name": "A2", "batch_id": ids["batch"], "intake_id": other_intake["id"], "semester_number": 6}).json()
        response = client.post(f"/api/v1/academic/sections/{wrong['id']}/routine/preview?intake_id={ids['intake']}&semester_number=6", headers=admin, files={"file": ("a2.csv", io.BytesIO(routine_csv(sections="A2")), "text/csv")})
        assert response.status_code == 422 and "Selected section does not belong" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
