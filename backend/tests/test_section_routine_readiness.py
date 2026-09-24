import io
import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import RoutineEntry, Student
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import ImportJob
from app.modules.scheduling.models import TimetableEntry


HEADER = "day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room\n"


def row(*, day: str, sections: str = "A1", module_code: str = "CT004-3-3", module_title: str = "Advanced Database Systems", class_type: str = "Lecture", lecturer_email: str = "karan@example.com", block: str = "Block B", room: str = "Machapuchare-L04", start: str = "08:30", end: str = "09:30") -> bytes:
    return (HEADER + ",".join([day, start, end, sections, module_code, module_title, class_type, lecturer_email, block, room]) + "\n").encode()


def test_section_import_readiness_projection_and_negative_validation():
    # Keep Semester 6 current so the student-facing current-routine endpoints
    # exercise their date-bounded visibility rather than a future semester.
    today = date.today()
    month_index = today.year * 12 + today.month - 1 - 30
    start_year, start_month = divmod(month_index, 12)
    batch_start = date(start_year, start_month + 1, 1)
    batch_end = batch_start.replace(year=batch_start.year + 3) - timedelta(days=1)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        with Session() as db:
            admin = User(name="Admin", email="admin@example.com", password_hash=hash_password("Password123!"), role=UserRole.ADMIN)
            db.add(admin)
            db.commit()

        def auth(email: str, password: str = "Password123!"):
            response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert response.status_code == 200, response.text
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        admin_headers = auth("admin@example.com")

        def calendar_pdf() -> bytes:
            buffer = io.BytesIO()
            writer = PdfWriter()
            writer.add_blank_page(width=144, height=144)
            writer.write(buffer)
            return buffer.getvalue()

        def create_level_with_calendars(batch_id: int, level_number: int, intake_code: str, first_start: date, first_end: date, second_start: date, second_end: date, intake_name: str | None = None):
            details = [
                {"display_name": f"Semester {level_number * 2 - 1}", "start_date": first_start.isoformat(), "end_date": first_end.isoformat()},
                {"display_name": f"Semester {level_number * 2}", "start_date": second_start.isoformat(), "end_date": second_end.isoformat()},
            ]
            response = client.post(
                "/api/v1/academic/levels/with-calendars",
                headers=admin_headers,
                data={
                    "batch_id": str(batch_id),
                    "level_number": str(level_number),
                    "intake_code": intake_code,
                    "intake_name": intake_name or "",
                    "semester_details": json.dumps(details),
                },
                files={
                    "semester_one_calendar": ("semester-one.pdf", calendar_pdf(), "application/pdf"),
                    "semester_two_calendar": ("semester-two.pdf", calendar_pdf(), "application/pdf"),
                },
            )
            assert response.status_code == 201, response.text
            return response.json()
        program = client.post("/api/v1/academic/programs", headers=admin_headers, json={"name": "BSc.IT"}).json()
        batch_response = client.post("/api/v1/academic/batches", headers=admin_headers, json={
            "name": "First batch",
            "program_id": program["id"],
            "start_date": batch_start.isoformat(),
            "end_date": batch_end.isoformat(),
        })
        assert batch_response.status_code == 200, batch_response.text
        batch = batch_response.json()
        create_level_with_calendars(batch["id"], 1, "SEP24", batch_start, batch_start + timedelta(days=50), batch_start + timedelta(days=75), batch_start + timedelta(days=150))
        create_level_with_calendars(batch["id"], 2, "SEP25", batch_start + timedelta(days=375), batch_start + timedelta(days=430), batch_start + timedelta(days=460), batch_start + timedelta(days=525))
        level_three = create_level_with_calendars(batch["id"], 3, "SEP26", today - timedelta(days=90), today - timedelta(days=31), today - timedelta(days=30), today + timedelta(days=30), "September 2026")
        cleared_name = client.patch(
            f"/api/v1/academic/levels/{level_three['id']}",
            headers=admin_headers,
            json={"intake_name": None},
        )
        assert cleared_name.status_code == 200 and cleared_name.json()["intake_name"] is None
        intake = next(item for item in client.get("/api/v1/academic/intakes", headers=admin_headers).json() if item["code"] == "SEP26")
        automatic_semesters = client.get("/api/v1/academic/cohort-semesters", headers=admin_headers).json()
        assert [item["semester_number"] for item in automatic_semesters] == [1, 2, 3, 4, 5, 6]

        second_batch_response = client.post("/api/v1/academic/batches", headers=admin_headers, json={
            "name": "Second batch",
            "program_id": program["id"],
            "start_date": batch_start.isoformat(),
            "end_date": batch_end.isoformat(),
        })
        assert second_batch_response.status_code == 200, second_batch_response.text
        second_batch = second_batch_response.json()
        for level_number, intake_code in ((1, "NPT1F2309IT"), (2, "NPT2F2409IT"), (3, "NPT3F2509IT")):
            offset = level_number * 100
            create_level_with_calendars(second_batch["id"], level_number, intake_code, batch_start + timedelta(days=offset), batch_start + timedelta(days=offset + 20), batch_start + timedelta(days=offset + 30), batch_start + timedelta(days=offset + 55))
        second_batch_semesters = [
            item for item in client.get("/api/v1/academic/cohort-semesters", headers=admin_headers).json()
            if item["batch_id"] == second_batch["id"]
        ]
        assert [(item["level_number"], item["semester_number"]) for item in second_batch_semesters] == [
            (1, 1), (1, 2), (2, 3), (2, 4), (3, 5), (3, 6),
        ]
        sections = {}
        for name in ("A1", "A2"):
            sections[name] = client.post("/api/v1/academic/sections", headers=admin_headers, json={"name": name, "batch_id": batch["id"]}).json()
        module = client.post("/api/v1/academic/modules", headers=admin_headers, json={"code": "CT004-3-3", "title": "Advanced Database Systems", "credits": 3, "semester_number": 6}).json()
        block = client.post("/api/v1/academic/blocks", headers=admin_headers, json={"name": "Block B"}).json()
        room = client.post("/api/v1/academic/rooms", headers=admin_headers, json={"block_id": block["id"], "name": "Machapuchare-L04", "room_type": "lecture", "capacity": 60}).json()
        room_two = client.post("/api/v1/academic/rooms", headers=admin_headers, json={"block_id": block["id"], "name": "Badimalika-LT07", "room_type": "lecture", "capacity": 60}).json()
        for name in ("Lecture", "Tutorial", "Practical"):
            client.post("/api/v1/academic/class-types", headers=admin_headers, json={"name": name})
        client.post("/api/v1/academic/time-slots", headers=admin_headers, json={"start_time": "08:30:00", "end_time": "09:30:00", "duration_label": "1h"})
        client.post("/api/v1/academic/time-slots", headers=admin_headers, json={"start_time": "10:00:00", "end_time": "11:00:00", "duration_label": "1h"})
        teacher = client.post("/api/v1/academic/teachers", headers=admin_headers, json={"name": "Karan Shrestha", "email": "karan@example.com", "password": "Password123!", "employee_code": "T-KARAN"}).json()
        teacher_two = client.post("/api/v1/academic/teachers", headers=admin_headers, json={"name": "Bina Shrestha", "email": "bina@example.com", "password": "Password123!", "employee_code": "T-BINA"}).json()
        offering = client.post("/api/v1/academic/module-offerings", headers=admin_headers, json={"academic_module_id": module["id"], "intake_id": intake["id"], "batch_id": batch["id"], "semester_number": 6, "section_ids": [sections["A1"]["id"], sections["A2"]["id"]]}).json()
        student = client.post("/api/v1/academic/students", headers=admin_headers, json={"name": "A1 Student", "email": "a1.student@example.com", "password": "Password123!", "section_id": sections["A1"]["id"], "roll_number": "A1-001", "subject_ids": []})
        assert student.status_code == 200, student.text

        day = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][datetime.now().weekday()]
        endpoint = f"/api/v1/academic/sections/{sections['A1']['id']}/routine"
        preview = client.post(f"{endpoint}/preview?intake_id={intake['id']}&semester_number=6", headers=admin_headers, files={"file": ("a1.csv", io.BytesIO(row(day=day)), "text/csv")})
        assert preview.status_code == 200 and (preview.json()["new_rows"], preview.json()["invalid_rows"]) == (1, 0)
        with Session() as db:
            assert db.scalar(select(RoutineEntry)) is None
            assert db.scalar(select(ImportJob)) is None
        imported = client.post(f"{endpoint}/import?intake_id={intake['id']}&semester_number=6", headers=admin_headers, files={"file": ("a1.csv", io.BytesIO(row(day=day)), "text/csv")})
        assert imported.status_code == 200 and imported.json()["success_count"] == 1

        merge_endpoint = f"/api/v1/academic/sections/{sections['A2']['id']}/routine"
        merged = client.post(f"{merge_endpoint}/preview?intake_id={intake['id']}&semester_number=6", headers=admin_headers, files={"file": ("a2.csv", io.BytesIO(row(day=day, sections="A2")), "text/csv")})
        assert merged.status_code == 200 and (merged.json()["merge_rows"], merged.json()["invalid_rows"]) == (1, 0)
        client.post(f"{merge_endpoint}/import?intake_id={intake['id']}&semester_number=6", headers=admin_headers, files={"file": ("a2.csv", io.BytesIO(row(day=day, sections="A2")), "text/csv")})
        duplicate = client.post(f"{endpoint}/preview?intake_id={intake['id']}&semester_number=6", headers=admin_headers, files={"file": ("combined.csv", io.BytesIO(row(day=day, sections="A1|A2")), "text/csv")})
        assert duplicate.status_code == 200 and (duplicate.json()["existing_rows"], duplicate.json()["invalid_rows"]) == (1, 0)

        with Session() as db:
            routines = db.scalars(select(RoutineEntry)).all()
            assert len(routines) == 1
            assert {link.section_id for link in routines[0].section_links} == {sections["A1"]["id"], sections["A2"]["id"]}
            assert db.scalar(select(TimetableEntry)) is None

        teacher_headers = auth("karan@example.com")
        student_headers = auth("a1.student@example.com")
        assert len(client.get("/api/v1/academic/teachers/me/routines", headers=teacher_headers).json()) == 1
        assert len(client.get("/api/v1/academic/routines/me", headers=student_headers).json()) == 1
        assert len(client.get(f"/api/v1/academic/routines/me/today", headers=student_headers).json()) == 1

        # Legacy accounts can be safely repaired only when their email identifies
        # exactly one unlinked student profile. The student still receives only
        # the routine for that profile's section.
        with Session() as db:
            legacy_student = db.scalar(select(Student).where(Student.email == "a1.student@example.com"))
            legacy_student.user_id = None
            db.commit()
        repaired = client.get("/api/v1/academic/routines/me", headers=student_headers)
        assert repaired.status_code == 200 and len(repaired.json()) == 1
        with Session() as db:
            linked_student = db.scalar(select(Student).where(Student.email == "a1.student@example.com"))
            assert linked_student.user_id is not None

        def invalid(payload: bytes, selected: str = "A1", selected_semester: int = 6):
            path = f"/api/v1/academic/sections/{sections[selected]['id']}/routine/preview?intake_id={intake['id']}&semester_number={selected_semester}"
            return client.post(path, headers=admin_headers, files={"file": ("invalid.csv", io.BytesIO(payload), "text/csv")})

        assert "No Academic Module matches module code 'MISSING'" in invalid(row(day=day, module_code="MISSING")).json()["errors"][0]["error_message"]
        assert "No teacher account/profile matches lecturer email 'missing@example.com'" in invalid(row(day=day, lecturer_email="missing@example.com")).json()["errors"][0]["error_message"]
        assert "Room 'Missing Room' does not exist in Block 'Block B'" in invalid(row(day=day, room="Missing Room")).json()["errors"][0]["error_message"]
        assert "Selected section 'A1' is not included in this row" in invalid(row(day=day, sections="A2")).json()["errors"][0]["error_message"]
        wrong_semester = invalid(row(day=day), selected_semester=7)
        assert wrong_semester.status_code == 422 and "does not belong to the requested academic context" in wrong_semester.json()["detail"]

        client.patch(f"/api/v1/academic/module-offerings/{offering['id']}/activation?is_active=false", headers=admin_headers)
        assert "No active course assignment exists" in invalid(row(day=day, start="10:00", end="11:00")).json()["errors"][0]["error_message"]
        client.patch(f"/api/v1/academic/module-offerings/{offering['id']}/activation?is_active=true", headers=admin_headers)

        teacher_conflict = invalid(row(day=day, sections="A2", room="Badimalika-LT07"), selected="A2")
        assert "Teacher conflict" in teacher_conflict.json()["errors"][0]["error_message"]
        room_conflict = invalid(row(day=day, sections="A2", lecturer_email="bina@example.com"), selected="A2")
        assert "Room conflict" in room_conflict.json()["errors"][0]["error_message"]
        section_conflict = invalid(row(day=day, sections="A1", lecturer_email="bina@example.com", room="Badimalika-LT07"))
        assert "Section conflict" in section_conflict.json()["errors"][0]["error_message"]
    finally:
        app.dependency_overrides.clear()
