import io
import json
from datetime import date

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicCalendar, CohortSemester
from app.modules.identity.models import User, UserRole


def calendar_pdf() -> bytes:
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=144, height=144)
    writer.write(stream)
    return stream.getvalue()


def test_level_intake_creates_admin_dated_semesters_and_course_assignment_context():
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
            db.add(User(
                name="Academic Administrator",
                email="academic.admin@example.com",
                password_hash=hash_password("Password123!"),
                role=UserRole.ADMIN,
            ))
            db.commit()

        login = client.post("/api/v1/auth/login", json={"email": "academic.admin@example.com", "password": "Password123!"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        program = client.post("/api/v1/academic/programs", headers=headers, json={"name": "Information Technology"}).json()

        def create_batch(name: str, start: date, end: date):
            response = client.post("/api/v1/academic/batches", headers=headers, json={
                "name": name,
                "program_id": program["id"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })
            assert response.status_code == 200, response.text
            return response.json()

        def create_level(batch_id: int, level_number: int, intake_code: str, details: list[dict[str, str]]):
            response = client.post(
                "/api/v1/academic/levels/with-calendars",
                headers=headers,
                data={
                    "batch_id": str(batch_id),
                    "level_number": str(level_number),
                    "intake_code": intake_code,
                    "semester_details": json.dumps(details),
                },
                files={
                    "semester_one_calendar": ("semester-one.pdf", calendar_pdf(), "application/pdf"),
                    "semester_two_calendar": ("semester-two.pdf", calendar_pdf(), "application/pdf"),
                },
            )
            return response

        september = create_batch("September 2023", date(2023, 9, 1), date(2026, 8, 31))
        level_one_details = [
            {"display_name": "Foundation Semester A", "start_date": "2023-09-18", "end_date": "2024-01-23"},
            {"display_name": "Foundation Semester B", "start_date": "2024-02-19", "end_date": "2024-06-07"},
        ]
        level_one = create_level(september["id"], 1, "NPT1F2309IT", level_one_details)
        assert level_one.status_code == 201, level_one.text
        assert level_one.json()["level_number"] == 1

        level_two_details = [
            {"display_name": "Semester III", "start_date": "2024-09-09", "end_date": "2025-01-31"},
            {"display_name": "Semester IV", "start_date": "2025-03-03", "end_date": "2025-07-25"},
        ]
        level_two = create_level(september["id"], 2, "NPT2F2409IT", level_two_details)
        assert level_two.status_code == 201, level_two.text

        level_three_details = [
            {"display_name": "Semester 5", "start_date": "2025-10-13", "end_date": "2026-02-06"},
            {"display_name": "Final Year Semester II", "start_date": "2026-03-16", "end_date": "2026-07-31"},
        ]
        level_three = create_level(september["id"], 3, "NPT3F2509IT", level_three_details)
        assert level_three.status_code == 201, level_three.text

        semesters = client.get("/api/v1/academic/cohort-semesters", headers=headers).json()
        september_semesters = [item for item in semesters if item["batch_id"] == september["id"]]
        assert [(item["level_number"], item["semester_number"]) for item in september_semesters] == [
            (1, 1), (1, 2), (2, 3), (2, 4), (3, 5), (3, 6),
        ]
        assert [(item["display_name"], item["start_date"], item["end_date"]) for item in september_semesters[:2]] == [
            ("Foundation Semester A", "2023-09-18", "2024-01-23"),
            ("Foundation Semester B", "2024-02-19", "2024-06-07"),
        ]
        assert september_semesters[0]["start_date"] != september["start_date"]
        assert all(item["calendar_uploaded"] for item in september_semesters)
        with Session() as db:
            assert db.scalar(select(func.count(AcademicCalendar.id))) == 6

        duplicate = create_level(september["id"], 3, "NPT3F2509IT", level_three_details)
        assert duplicate.status_code == 409
        assert len([item for item in client.get("/api/v1/academic/cohort-semesters", headers=headers).json() if item["batch_id"] == september["id"]]) == 6

        september_five = next(item for item in september_semesters if item["semester_number"] == 5)
        rename = client.patch(
            f"/api/v1/academic/cohort-semesters/{september_five['id']}",
            headers=headers,
            json={"display_name": "Semester V"},
        )
        assert rename.status_code == 200, rename.text
        assert rename.json()["display_name"] == "Semester V"
        assert rename.json()["semester_number"] == 5

        january = create_batch("January 2024", date(2024, 1, 15), date(2027, 1, 14))
        january_level_three = create_level(january["id"], 3, "NPT3F2601IT", [
            {"display_name": "Semester 5", "start_date": "2026-01-12", "end_date": "2026-05-08"},
            {"display_name": "Semester 6", "start_date": "2026-06-01", "end_date": "2026-10-02"},
        ])
        assert january_level_three.status_code == 201, january_level_three.text
        semesters = client.get("/api/v1/academic/cohort-semesters", headers=headers).json()
        january_five = next(item for item in semesters if item["batch_id"] == january["id"] and item["semester_number"] == 5)
        refreshed_september_five = next(item for item in semesters if item["id"] == september_five["id"])
        assert january_five["id"] != refreshed_september_five["id"]
        assert january_five["display_name"] == "Semester 5"
        assert refreshed_september_five["display_name"] == "Semester V"

        batches = client.get("/api/v1/academic/batches", headers=headers).json()
        september_batch = next(item for item in batches if item["id"] == september["id"])
        january_batch = next(item for item in batches if item["id"] == january["id"])
        assert [item["intake_code"] for item in september_batch["levels"]] == ["NPT1F2309IT", "NPT2F2409IT", "NPT3F2509IT"]
        assert [item["intake_code"] for item in january_batch["levels"]] == ["NPT3F2601IT"]
        assert [item["semester_number"] for item in semesters if item["batch_id"] == september["id"] and item["batch_level_id"] == level_three.json()["id"]] == [5, 6]

        a1 = client.post("/api/v1/academic/sections", headers=headers, json={"name": "A1", "batch_id": september["id"]}).json()
        a2 = client.post("/api/v1/academic/sections", headers=headers, json={"name": "A2", "batch_id": september["id"]}).json()
        b1 = client.post("/api/v1/academic/sections", headers=headers, json={"name": "B1", "batch_id": january["id"]}).json()
        course = client.post("/api/v1/academic/modules", headers=headers, json={"code": "CT097-3-3-CSVC", "title": "Cloud Infrastructure and Services", "credits": 3, "semester_number": 5}).json()
        september_intake = next(item for item in client.get("/api/v1/academic/intakes", headers=headers).json() if item["code"] == "NPT3F2509IT")
        assignment = client.post("/api/v1/academic/module-offerings", headers=headers, json={
            "academic_module_id": course["id"],
            "intake_id": september_intake["id"],
            "batch_id": september["id"],
            "semester_number": 5,
            "section_ids": [a1["id"], a2["id"]],
            "is_active": True,
        })
        assert assignment.status_code == 200, assignment.text
        assert assignment.json()["cohort_semester_id"] == refreshed_september_five["id"]
        assert assignment.json()["section_names"] == ["A1", "A2"]
        september_six = next(item for item in semesters if item["batch_id"] == september["id"] and item["semester_number"] == 6)
        reassigned = client.patch(f"/api/v1/academic/module-offerings/{assignment.json()['id']}", headers=headers, json={
            "intake_id": september_intake["id"],
            "batch_id": september["id"],
            "semester_number": 6,
            "section_ids": [a1["id"], a2["id"]],
        })
        assert reassigned.status_code == 200, reassigned.text
        assert reassigned.json()["cohort_semester_id"] == september_six["id"]
        wrong_batch_section = client.post("/api/v1/academic/module-offerings", headers=headers, json={
            "academic_module_id": course["id"],
            "intake_id": september_intake["id"],
            "batch_id": september["id"],
            "semester_number": 6,
            "section_ids": [b1["id"]],
        })
        assert wrong_batch_section.status_code == 422

        with Session() as db:
            persisted = db.scalar(select(CohortSemester).where(CohortSemester.id == refreshed_september_five["id"]))
            assert persisted.semester_number == 5
            assert persisted.display_name == "Semester V"
    finally:
        app.dependency_overrides.clear()