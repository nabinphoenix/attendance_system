from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, Section, Teacher, TimeSlot
from app.modules.academic.module_offering_service import validate_routine_entry_module_offering
from app.modules.identity.models import User, UserRole


def test_module_offering_admin_crud_validation_filters_and_routine_safety():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with Session() as db:
        program = Program(name="IT")
        other_program = Program(name="Business")
        db.add_all([program, other_program])
        db.flush()
        intake = Intake(name="September", code="SEP", start_date=date(2026, 9, 1), program_id=program.id)
        other_intake = Intake(name="January", code="JAN", start_date=date(2027, 1, 1), program_id=program.id)
        batch = Batch(name="2026", program_id=program.id)
        second_batch = Batch(name="2027", program_id=program.id)
        other_batch = Batch(name="Business 2026", program_id=other_program.id)
        module = AcademicModule(code="CT004", title="Databases", credits=3, semester_number=6)
        wrong_semester_module = AcademicModule(code="CT005", title="Networks", credits=3, semester_number=5)
        db.add_all([intake, other_intake, batch, second_batch, other_batch, module, wrong_semester_module])
        db.flush()
        section = Section(name="A1", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        unused_section = Section(name="A2", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        wrong_batch_section = Section(name="B1", batch_id=second_batch.id, intake_id=intake.id, semester_number=6)
        wrong_intake_section = Section(name="A3", batch_id=batch.id, intake_id=other_intake.id, semester_number=6)
        wrong_semester_section = Section(name="A4", batch_id=batch.id, intake_id=intake.id, semester_number=7)
        admin = User(name="Admin", email="admin@example.com", password_hash=hash_password("Password123!"), role=UserRole.ADMIN)
        student = User(name="Student", email="student@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
        db.add_all([section, unused_section, wrong_batch_section, wrong_intake_section, wrong_semester_section, admin, student])
        db.commit()
        ids = {"module": module.id, "wrong_module": wrong_semester_module.id, "intake": intake.id, "batch": batch.id, "other_batch": other_batch.id, "section": section.id, "unused": unused_section.id, "wrong_batch": wrong_batch_section.id, "wrong_intake": wrong_intake_section.id, "wrong_semester": wrong_semester_section.id}

    client = TestClient(app)
    def headers(email: str):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    admin_headers = headers("admin@example.com")
    student_headers = headers("student@example.com")
    payload = {"academic_module_id": ids["module"], "intake_id": ids["intake"], "batch_id": ids["batch"], "semester_number": 6}
    assert client.post("/api/v1/academic/module-offerings", headers=student_headers, json=payload).status_code == 403
    created = client.post("/api/v1/academic/module-offerings", headers=admin_headers, json=payload)
    assert created.status_code == 200, created.text
    offering_id = created.json()["id"]
    assert created.json()["module_code"] == "CT004"
    assert created.json()["section_names"] == ["A1", "A2"]
    assert client.post("/api/v1/academic/module-offerings", headers=admin_headers, json=payload).status_code == 409
    for invalid in (
        {**payload, "batch_id": ids["other_batch"]},
        {**payload, "academic_module_id": ids["wrong_module"]},
    ):
        assert client.post("/api/v1/academic/module-offerings", headers=admin_headers, json=invalid).status_code == 422
    for query in (f"academic_module_id={ids['module']}", f"intake_id={ids['intake']}", f"batch_id={ids['batch']}", "semester_number=6", f"section_id={ids['section']}", f"section_id={ids['unused']}"):
        listed = client.get(f"/api/v1/academic/module-offerings?{query}", headers=admin_headers)
        assert listed.status_code == 200 and [item["id"] for item in listed.json()] == [offering_id]

    added = client.patch(f"/api/v1/academic/module-offerings/{offering_id}", headers=admin_headers, json={"section_ids": [ids["section"]]})
    assert added.status_code == 200 and set(added.json()["section_ids"]) == {ids["section"], ids["unused"]}
    inherited = client.post("/api/v1/academic/sections", headers=admin_headers, json={"name": "A5", "batch_id": ids["batch"], "intake_id": ids["intake"], "semester_number": 6})
    assert inherited.status_code == 200, inherited.text
    a5_id = inherited.json()["id"]
    reloaded = client.get(f"/api/v1/academic/module-offerings/{offering_id}", headers=admin_headers)
    assert reloaded.status_code == 200 and set(reloaded.json()["section_ids"]) == {ids["section"], ids["unused"], a5_id}

    with Session() as db:
        offering = db.get(ModuleOffering, offering_id)
        block = Block(name="Block B")
        kind = ClassType(name="Lecture")
        slot = TimeSlot(start_time=time(8, 30), end_time=time(9, 30), duration_label="1h")
        teacher_user = User(name="Teacher", email="teacher@example.com", password_hash="x", role=UserRole.TEACHER)
        db.add_all([block, kind, slot, teacher_user])
        db.flush()
        room = Room(block_id=block.id, name="L04", room_type="lecture", capacity=60)
        teacher = Teacher(user_id=teacher_user.id, employee_code="T1")
        db.add_all([room, teacher])
        db.flush()
        routine = RoutineEntry(intake_id=ids["intake"], semester_number=6, section_id=ids["section"], module_id=ids["module"], module_offering_id=offering_id, class_type_id=kind.id, teacher_id=teacher.id, room_id=room.id, day_of_week=1, time_slot_id=slot.id)
        db.add(routine)
        db.commit()
        validate_routine_entry_module_offering(db, routine, offering)
        routine.module_offering_id = offering_id
        routine.section_id = ids["unused"]
        db.add(routine)
        db.flush()
        validate_routine_entry_module_offering(db, routine, offering)
        db.rollback()

    retained = client.patch(f"/api/v1/academic/module-offerings/{offering_id}", headers=admin_headers, json={"section_ids": []})
    assert retained.status_code == 200 and set(retained.json()["section_ids"]) == {ids["section"], ids["unused"], a5_id}
    assert client.patch(f"/api/v1/academic/module-offerings/{offering_id}/activation?is_active=false", headers=admin_headers).json()["is_active"] is False
    assert client.delete(f"/api/v1/academic/module-offerings/{offering_id}", headers=admin_headers).status_code == 409
    app.dependency_overrides.clear()
