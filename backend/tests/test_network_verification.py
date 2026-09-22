from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch, Program, Section, Student, StudentSubjectEnrollment, Subject, Teacher
from app.modules.attendance.models import AttendanceRecord, CampusNetwork, CheckInAttempt
from app.modules.attendance.network import classify_ip
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, TimetableEntry


@pytest.fixture
def attendance_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        program = Program(name="BCA", college_id=1)
        batch = Batch(name="2026", program_id=1, college_id=1)
        section = Section(name="A", batch_id=1, college_id=1)
        subject = Subject(name="Architecture", code="ARC", section_id=1)
        teacher_user = User(
            name="Teacher",
            email="network-teacher@example.com",
            password_hash=hash_password("Password123!"),
            role=UserRole.TEACHER,
            college_id=1,
        )
        student_user = User(
            name="Student",
            email="network-student@example.com",
            password_hash=hash_password("Password123!"),
            role=UserRole.STUDENT,
            college_id=1,
        )
        db.add_all([program, batch, section, subject, teacher_user, student_user])
        db.flush()
        teacher = Teacher(user_id=teacher_user.id, employee_code="NT1", college_id=1)
        student = Student(
            user_id=student_user.id,
            section_id=section.id,
            roll_number="N1",
            name=student_user.name,
            email=student_user.email,
            subjects=[subject],
            college_id=1,
        )
        db.add_all([teacher, student])
        db.flush()
        db.add(
            TimetableEntry(
                teacher_id=teacher.id,
                subject_id=subject.id,
                section_id=section.id,
                day_of_week=datetime.now().weekday(),
                start_time=(datetime.now() - timedelta(hours=1)).time(),
                end_time=(datetime.now() + timedelta(hours=1)).time(),
                room_name="Lab",
                latitude=27.7172,
                longitude=85.3240,
                college_id=1,
            )
        )
        db.add(
            CampusNetwork(
                label="Campus IPv4",
                cidr="198.51.100.0/24",
                created_by=teacher_user.id,
                college_id=1,
            )
        )
        db.commit()
        entry_id = db.scalar(select(TimetableEntry.id))

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        def auth(email: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "Password123!"},
            )
            assert response.status_code == 200, response.text
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        yield client, session_factory, entry_id, auth("network-teacher@example.com"), auth("network-student@example.com")
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def college_network_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        from app.modules.platform.models import College

        db.add(College(id=2, name="Second College", slug="second-network", is_active=True))
        db.add_all(
            [
                User(
                    name="College Admin One",
                    email="network-admin-one@example.com",
                    password_hash=hash_password("Password123!"),
                    role=UserRole.ADMIN,
                    college_id=1,
                ),
                User(
                    name="College Admin Two",
                    email="network-admin-two@example.com",
                    password_hash=hash_password("Password123!"),
                    role=UserRole.ADMIN,
                    college_id=2,
                ),
            ]
        )
        db.commit()

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        def auth(email: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "Password123!"},
            )
            assert response.status_code == 200, response.text
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        yield client, session_factory, auth("network-admin-one@example.com"), auth("network-admin-two@example.com")
    app.dependency_overrides.clear()
    engine.dispose()


def test_classify_ip_matches_multiple_ipv4_and_ipv6_ranges():
    cidrs = ["192.0.2.0/24", "2001:db8:1234::/48"]

    assert classify_ip("192.0.2.44", cidrs, None, None) == "campus"
    assert classify_ip("2001:db8:1234::44", cidrs, None, None) == "campus"
    assert classify_ip("203.0.113.44", cidrs, None, None) == "outside"
    assert classify_ip("2001:db8:9999::44", cidrs, None, None) == "outside"


def test_loopback_is_unknown_and_teacher_status_controls_same_as_teacher():
    assert classify_ip("127.0.0.1", ["127.0.0.0/8"], None, None) == "unknown"
    assert classify_ip("::1", ["::1/128"], None, None) == "unknown"
    assert classify_ip("203.0.113.44", [], "203.0.113.44", "outside") == "outside"
    assert classify_ip("203.0.113.44", [], "203.0.113.44", "campus") == "same_as_teacher"


def test_start_twice_keeps_original_teacher_ip(attendance_context):
    client, session_factory, entry_id, teacher_headers, _ = attendance_context

    first = client.post(
        f"/api/v1/sessions/{entry_id}/start",
        headers=teacher_headers | {"X-Forwarded-For": "198.51.100.10"},
    )
    second = client.post(
        f"/api/v1/sessions/{entry_id}/start",
        headers=teacher_headers | {"X-Forwarded-For": "198.51.100.11"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    with session_factory() as db:
        session = db.get(ClassSession, first.json()["id"])
        assert session.teacher_ip == "198.51.100.10"
        assert session.teacher_ip_status == "campus"


def test_student_ip_can_differ_between_check_in_steps(attendance_context):
    client, session_factory, entry_id, teacher_headers, student_headers = attendance_context
    started = client.post(
        f"/api/v1/sessions/{entry_id}/start",
        headers=teacher_headers | {"X-Forwarded-For": "198.51.100.10"},
    )
    assert started.status_code == 200, started.text
    session_id = started.json()["id"]
    challenge = client.get(f"/api/v1/sessions/{session_id}/qr", headers=teacher_headers)
    assert challenge.status_code == 200, challenge.text

    scanned = client.post(
        "/api/v1/check-ins",
        headers=student_headers | {"X-Forwarded-For": "198.51.100.20"},
        json={"qr_token": challenge.json()["token"], "latitude": 27.7172, "longitude": 85.3240, "accuracy": 5},
    )
    assert scanned.status_code == 200, scanned.text
    confirmed = client.post(
        "/api/v1/check-ins/confirm",
        headers=student_headers | {"X-Forwarded-For": "203.0.113.20"},
        json={"verification_token": scanned.json()["verification_token"], "code": challenge.json()["classroom_code"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    with session_factory() as db:
        attempt = db.scalar(select(CheckInAttempt).where(CheckInAttempt.class_session_id == session_id))
        record = db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id == session_id))
        assert attempt.client_ip == "198.51.100.20"
        assert attempt.ip_status == "campus"
        assert attempt.confirm_client_ip == "203.0.113.20"
        assert attempt.confirm_ip_status == "outside"
        assert record.ip_status == "outside"
        assert record.network_method == "public_ip"


def test_admin_networks_are_college_scoped_and_wide_ranges_need_force(college_network_context):
    client, session_factory, admin_one, admin_two = college_network_context

    rejected = client.post(
        "/api/v1/campus-networks",
        headers=admin_one,
        json={"label": "Too wide", "cidr": "10.0.0.0/8"},
    )
    assert rejected.status_code == 422
    created = client.post(
        "/api/v1/campus-networks",
        headers=admin_one,
        json={"label": "College One", "cidr": "10.0.0.0/8", "force": True},
    )
    assert created.status_code == 201, created.text
    network_id = created.json()["id"]

    assert len(client.get("/api/v1/campus-networks", headers=admin_one).json()) == 1
    assert client.get("/api/v1/campus-networks", headers=admin_two).json() == []
    assert client.post(
        f"/api/v1/campus-networks/{network_id}/deactivate",
        headers=admin_two,
    ).status_code == 404

    confirmed = client.post(
        "/api/v1/campus-networks/current/confirm",
        headers=admin_two | {"X-Forwarded-For": "203.0.113.40"},
        json={"label": "Current network"},
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["cidr"] == "203.0.113.40/32"
    assert len(client.get("/api/v1/campus-networks", headers=admin_one).json()) == 1
    assert len(client.get("/api/v1/campus-networks", headers=admin_two).json()) == 1

    with session_factory() as db:
        assert db.scalar(select(CampusNetwork).where(CampusNetwork.id == network_id)).is_active is True