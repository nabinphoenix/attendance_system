from datetime import date, time
from io import BytesIO
import importlib

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.modules.academic.models import (
    AcademicCalendar, AcademicModule, Batch, Block, ClassType, CohortSemester,
    Intake, Program, Room, RoutineEntry, RoutineEntrySection, Section, Student,
    StudentEnrollment, Teacher, TeacherFeedback, TimeSlot,
)
from app.modules.academic import semester_resource_service as service
from app.modules.academic import semester_resource_router as router
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import AuditLog
from app.modules.platform.models import College

BASE = "/api/v1/academic/semester-resources/semesters"
DAY = date(2026, 3, 15)


def pdf_bytes(*, encrypted=False, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("test-secret")
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(service, "today", lambda: DAY)
    monkeypatch.setattr(router, "today", lambda: DAY)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(College(id=2, name="Other college", slug="other", is_active=True))
        db.flush()
        specs = [
            (1, UserRole.ADMIN, 1), (2, UserRole.STUDENT, 1),
            (3, UserRole.TEACHER, 1), (4, UserRole.TEACHER, 1),
            (5, UserRole.ADMIN, 2), (6, UserRole.PARENT, 1),
            (7, UserRole.SUPER_ADMIN, None),
        ]
        for identifier, role, college_id in specs:
            db.add(User(id=identifier, name=f"User {identifier}", email=f"user{identifier}@example.com",
                        role=role, college_id=college_id, password_hash="unused-in-token-tests"))
        db.add_all([Program(id=1, name="Computing", college_id=1),
                    Program(id=2, name="Computing", college_id=2)])
        db.flush()
        for identifier, program_id, college_id in [(1, 1, 1), (2, 1, 1), (3, 2, 2)]:
            db.add(Batch(id=identifier, name=f"Batch {identifier}", program_id=program_id, college_id=college_id))
            db.add(Intake(id=identifier, name=f"Intake {identifier}", code=f"I{identifier}",
                          start_date=date(2026, 1, 1), program_id=program_id, college_id=college_id))
        db.flush()
        for identifier, college_id in [(1, 1), (2, 1), (3, 2)]:
            db.add(CohortSemester(id=identifier, intake_id=identifier, batch_id=identifier,
                                 semester_number=1, start_date=date(2026, 1, 1),
                                 end_date=date(2026, 6, 30), college_id=college_id))
        for identifier in (1, 2, 3):
            db.add(Section(id=identifier, name=f"Section {identifier}", batch_id=1, intake_id=1, semester_number=1))
        db.add_all([
            Teacher(id=1, user_id=3, employee_code="T1"),
            Teacher(id=2, user_id=4, employee_code="T2"),
            AcademicModule(id=1, code="M1", title="Module", credits=3, semester_number=1),
            ClassType(id=1, name="Lecture"), Block(id=1, name="Block"),
            TimeSlot(id=1, start_time=time(9), end_time=time(10), duration_label="1h"),
        ])
        db.flush()
        db.add_all([Room(id=1, name="Room", room_type="lecture", capacity=30, block_id=1),
                    Student(id=1, user_id=2, section_id=1, roll_number="S1")])
        db.flush()
        db.add(StudentEnrollment(student_id=1, section_id=1, cohort_semester_id=1, starts_on=date(2026, 1, 1)))
        # Teacher 1 teaches a combined class whose primary section is not the
        # student's section. Teacher 2 teaches another section in this cohort.
        for identifier, section_id in [(1, 2), (2, 3)]:
            db.add(RoutineEntry(id=identifier, intake_id=1, semester_number=1, cohort_semester_id=1,
                                section_id=section_id, module_id=1, class_type_id=1, teacher_id=identifier,
                                room_id=1, day_of_week=identifier, time_slot_id=1))
        db.flush()
        db.add(RoutineEntrySection(routine_entry_id=1, section_id=1))
        db.commit()

    def override():
        with factory() as db:
            db.info["college_id"] = -1
            yield db
    app.dependency_overrides[get_db] = override
    headers = {name: {"Authorization": "Bearer " + create_access_token(str(identifier))}
               for name, identifier in [("admin", 1), ("student", 2), ("teacher", 3), ("other_teacher", 4),
                                        ("other_admin", 5), ("parent", 6), ("root", 7)]}
    try:
        with TestClient(app) as client:
            yield client, headers, factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def form(**overrides):
    return {
        "title": "Mid-semester feedback", "form_url": "https://forms.gle/Feedback123",
        "opens_on": "2026-03-01", "closes_on": "2026-03-31", "is_published": True,
        **overrides,
    }


def test_calendar_upload_replace_download_remove_and_private_audit(context):
    client, h, factory = context
    first = pdf_bytes()
    response = client.put(f"{BASE}/1/calendar", headers=h["admin"],
                          files={"file": ("../calendar.pdf", first, "application/octet-stream")})
    assert response.status_code == 200, response.text
    original_id = response.json()["id"]
    assert response.json()["filename"] == "calendar.pdf"
    assert response.json()["size_bytes"] == len(first)
    assert "pdf_data" not in response.json()
    for role in ("admin", "student", "teacher"):
        response = client.get(f"{BASE}/1/calendar", headers=h[role])
        assert response.status_code == 200, response.text
        assert response.content == first
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "private, no-store"
        assert "attachment" in response.headers["content-disposition"]
    second = pdf_bytes(pages=2)
    response = client.put(f"{BASE}/1/calendar", headers=h["admin"],
                          files={"file": ("revised.pdf", second, "application/pdf")})
    assert response.json()["id"] == original_id
    assert client.get(f"{BASE}/1/calendar", headers=h["student"]).content == second
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AcademicCalendar)) == 1
        audits = db.scalars(select(AuditLog).where(AuditLog.entity_type == "academic_calendars")).all()
        assert audits
        assert all("pdf_data" not in row.details for row in audits)
    assert client.delete(f"{BASE}/1/calendar", headers=h["admin"]).status_code == 204
    assert client.get(f"{BASE}/1/calendar", headers=h["student"]).status_code == 404
    assert client.get(BASE, headers=h["student"]).json()[0]["calendar"] is None


@pytest.mark.parametrize("filename,content,status", [
    ("calendar.txt", b"not a PDF", 422),
    ("calendar.pdf", b"%PDF-1.7\nfake\n%%EOF", 422),
    ("calendar.pdf", b"", 422),
    ("calendar.pdf", pdf_bytes(encrypted=True), 422),
    ("calendar.pdf", pdf_bytes(pages=0), 422),
    ("calendar.pdf", b"x" * (service.MAX_CALENDAR_BYTES + 1), 413),
], ids=["wrong-type", "malformed", "empty", "encrypted", "no-pages", "oversized"])
def test_bad_uploads_preserve_existing_calendar(context, filename, content, status):
    client, h, _ = context
    original = pdf_bytes()
    assert client.put(f"{BASE}/1/calendar", headers=h["admin"],
                      files={"file": ("valid.pdf", original, "application/pdf")}).status_code == 200
    response = client.put(f"{BASE}/1/calendar", headers=h["admin"],
                          files={"file": (filename, content, "application/pdf")})
    assert response.status_code == status, response.text
    assert client.get(f"{BASE}/1/calendar", headers=h["student"]).content == original


def test_resource_access_roles_and_colleges(context):
    client, h, _ = context
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=h["parent"]).status_code == 403
    for role in ("student", "teacher"):
        assert [row["id"] for row in client.get(BASE, headers=h[role]).json()] == [1]
        assert client.get(f"{BASE}/2/calendar", headers=h[role]).status_code == 404
        assert client.get(f"{BASE}/1/teachers", headers=h[role]).status_code == 403
        assert client.put(f"{BASE}/1/calendar", headers=h[role],
                          files={"file": ("calendar.pdf", pdf_bytes(), "application/pdf")}).status_code == 403
        assert client.delete(f"{BASE}/1/calendar", headers=h[role]).status_code == 403
        assert client.put(f"{BASE}/1/feedback/1", headers=h[role], json=form()).status_code == 403
        assert client.delete(f"{BASE}/1/feedback/1", headers=h[role]).status_code == 403
    assert client.get(f"{BASE}/1/feedback", headers=h["teacher"]).status_code == 403
    assert [row["id"] for row in client.get(BASE, headers=h["other_admin"]).json()] == [3]
    assert client.put(f"{BASE}/3/calendar", headers=h["admin"],
                      files={"file": ("calendar.pdf", pdf_bytes(), "application/pdf")}).status_code == 404
    assert client.put(f"{BASE}/3/feedback/1", headers=h["admin"], json=form()).status_code == 404
    assert client.get(f"{BASE}/1/feedback", headers=h["other_admin"]).status_code == 404
    assert client.get(BASE, headers=h["admin"] | {"X-College-ID": "2"}).status_code == 403
    assert client.get(BASE, headers=h["root"]).status_code == 400
    response = client.put(f"{BASE}/3/calendar", headers=h["root"] | {"X-College-ID": "2"},
                          files={"file": ("calendar.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 200, response.text


def test_feedback_is_one_per_teacher_per_semester_and_only_own_teachers(context):
    client, h, factory = context
    teachers = client.get(f"{BASE}/1/teachers", headers=h["admin"]).json()
    assert {row["id"] for row in teachers} == {1, 2}
    first = client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form())
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "open"
    updated = client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form(title="Updated"))
    assert updated.status_code == 200
    assert updated.json()["id"] == first.json()["id"]
    assert client.put(f"{BASE}/1/feedback/2", headers=h["admin"], json=form()).status_code == 200
    forms = client.get(f"{BASE}/1/feedback", headers=h["student"]).json()
    assert len(forms) == 1
    assert forms[0]["teacher_id"] == 1
    assert forms[0]["title"] == "Updated"
    assert forms[0]["form_url"] == form()["form_url"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TeacherFeedback)) == 2
    assert client.delete(f"{BASE}/1/feedback/1", headers=h["admin"]).status_code == 204
    assert client.get(f"{BASE}/1/feedback", headers=h["student"]).json() == []


@pytest.mark.parametrize("changes,expected,visible,linked", [
    ({"is_published": False}, "draft", False, False),
    ({"opens_on": "2026-04-01", "closes_on": "2026-04-15"}, "scheduled", True, False),
    ({"opens_on": "2026-02-01", "closes_on": "2026-02-15"}, "closed", True, False),
    ({"opens_on": "2026-03-15", "closes_on": "2026-03-15"}, "open", True, True),
])
def test_feedback_publication_and_window_boundaries(context, changes, expected, visible, linked):
    client, h, _ = context
    response = client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form(**changes))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == expected
    assert response.json()["form_url"]
    student_forms = client.get(f"{BASE}/1/feedback", headers=h["student"]).json()
    assert bool(student_forms) == visible
    if visible:
        assert bool(student_forms[0]["form_url"]) == linked


@pytest.mark.parametrize("url", [
    "https://example.com/forms/test", "javascript:alert(1)", "http://forms.gle/Form123",
    "https://forms.gle.evil.example/Form123", "https://forms.gle@evil.example/Form123",
    "https://docs.google.com/forms/d/Form123/edit", "https://docs.google.com/spreadsheets/d/123/edit",
    "https://forms.gle:444/Form123", "https://forms.gle/Form123\nmalicious",
])
def test_feedback_rejects_non_responder_links(context, url):
    client, h, _ = context
    response = client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form(form_url=url))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("url", [
    "https://forms.gle/Form123",
    "https://docs.google.com/forms/d/e/Form123/viewform?usp=sf_link",
    "https://docs.google.com/forms/d/Form123/viewform",
    "https://docs.google.com/forms/u/0/d/e/Form123/viewform?embedded=true",
])
def test_feedback_accepts_google_responder_links(context, url):
    client, h, _ = context
    response = client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form(form_url=url))
    assert response.status_code == 200, response.text


def test_feedback_rejects_bad_dates_and_unassigned_teachers(context):
    client, h, _ = context
    for changes in [
        {"opens_on": "2025-12-31"}, {"closes_on": "2026-07-01"},
        {"opens_on": "2026-04-30", "closes_on": "2026-04-01"}, {"title": "  "},
    ]:
        assert client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form(**changes)).status_code == 422
    assert client.put(f"{BASE}/2/feedback/1", headers=h["admin"], json=form()).status_code == 422
    assert client.put(f"{BASE}/1/feedback/999", headers=h["admin"], json=form()).status_code == 422


def test_legacy_students_and_routines_match_complete_semester_context(context):
    client, h, factory = context
    with factory() as db:
        db.delete(db.scalar(select(StudentEnrollment)))
        db.get(RoutineEntry, 1).cohort_semester_id = None
        db.commit()
    assert client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form()).status_code == 200
    assert [row["teacher_id"] for row in client.get(f"{BASE}/1/feedback", headers=h["student"]).json()] == [1]
    with factory() as db:
        db.get(Section, 1).intake_id = 2
        db.commit()
    assert client.get(BASE, headers=h["student"]).json() == []


def test_ended_and_withdrawn_enrollment_cannot_receive_current_feedback(context):
    client, h, factory = context
    assert client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form()).status_code == 200
    with factory() as db:
        enrollment = db.scalar(select(StudentEnrollment))
        enrollment.ends_on = DAY
        enrollment.status = "completed"
        db.commit()
    # History retains the calendar, without reviving an ended placement.
    assert [row["id"] for row in client.get(BASE, headers=h["student"]).json()] == [1]
    assert client.get(f"{BASE}/1/feedback", headers=h["student"]).json() == []
    with factory() as db:
        db.scalar(select(StudentEnrollment)).status = "withdrawn"
        db.commit()
    assert client.get(BASE, headers=h["student"]).json() == []


def test_resource_migration_upgrade_and_downgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    migration = importlib.import_module("migrations.versions.j4e5f6g7h8i9_semester_resources")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            inspector = inspect(connection)
            assert {"academic_calendars", "teacher_feedback"} <= set(inspector.get_table_names())
            assert inspector.get_unique_constraints("teacher_feedback")[0]["column_names"] == ["cohort_semester_id", "teacher_id"]
            migration.downgrade()
            assert not ({"academic_calendars", "teacher_feedback"} & set(inspect(connection).get_table_names()))
    engine.dispose()

def test_teacher_with_feedback_cannot_be_deleted_after_routine_removal(context):
    client, h, factory = context
    assert client.put(f"{BASE}/1/feedback/1", headers=h["admin"], json=form()).status_code == 200
    with factory() as db:
        db.delete(db.get(RoutineEntry, 1))
        db.commit()
    assert client.delete("/api/v1/academic/teachers/1", headers=h["admin"]).status_code == 409
    # The admin can still edit or remove this now-unassigned teacher's form.
    assert client.put(f"{BASE}/1/feedback/1", headers=h["admin"],
                      json=form(is_published=False)).status_code == 200
    assert client.get(f"{BASE}/1/feedback", headers=h["student"]).json() == []
    assert client.delete(f"{BASE}/1/feedback/1", headers=h["admin"]).status_code == 204


def test_resource_access_uses_existing_legacy_profile_linking(context):
    client, h, factory = context
    with factory() as db:
        student = db.get(Student, 1)
        student.user_id = None
        student.email = "user2@example.com"
        db.commit()
    assert [row["id"] for row in client.get(BASE, headers=h["student"]).json()] == [1]
    with factory() as db:
        assert db.get(Student, 1).user_id == 2
