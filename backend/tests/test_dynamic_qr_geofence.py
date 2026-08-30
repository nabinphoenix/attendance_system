from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import (
    AcademicModule,
    Batch,
    Block,
    ClassType,
    Intake,
    Program,
    Room,
    RoutineEntry,
    RoutineEntrySection,
    Section,
    Student,
    Teacher,
    TimeSlot,
)
from app.modules.attendance.models import AttendanceChallenge, AttendanceRecord, CheckInAttempt, CheckInAttemptStatus, PendingAttendanceVerification
from app.modules.attendance.router import validate_current_rotation
from app.modules.attendance.service import QRValidationError, validate_qr_token
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import AuditLog
from app.modules.scheduling.models import ClassSession, OverrideStatus, ScheduleOverride, SessionStatus


PASSWORD = "Password123!"
ROOM_LATITUDE = 27.7172
ROOM_LONGITUDE = 85.3240


@pytest.fixture()
def attendance_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestSession() as db:
        program = Program(name="IT")
        db.add(program)
        db.flush()
        intake = Intake(name="September", code="SEP-2026", start_date=date(2026, 9, 1), program_id=program.id)
        batch = Batch(name="2026", program_id=program.id)
        db.add_all([intake, batch])
        db.flush()
        sections = {name: Section(name=name, batch_id=batch.id, intake_id=intake.id, semester_number=6) for name in ("A2", "A3", "A4")}
        module = AcademicModule(code="ADB", title="Advanced Database Systems", credits=3, semester_number=6)
        block = Block(name="Block B")
        db.add_all([*sections.values(), module, block])
        db.flush()
        original_room = Room(
            block_id=block.id,
            name="Machapuchare-L04",
            room_type="lecture",
            capacity=60,
            latitude=ROOM_LATITUDE,
            longitude=ROOM_LONGITUDE,
            geofence_radius_meters=50,
        )
        override_room = Room(
            block_id=block.id,
            name="Annapurna",
            room_type="lecture",
            capacity=60,
            latitude=27.7200,
            longitude=85.3300,
            geofence_radius_meters=35,
        )
        missing_room = Room(block_id=block.id, name="No GPS", room_type="lecture", capacity=60)
        class_type = ClassType(name="Lecture")
        slot = TimeSlot(start_time=time(8, 30), end_time=time(9, 30), duration_label="1h")
        db.add_all([original_room, override_room, missing_room, class_type, slot])
        users = {}
        for key, role in (
            ("teacher", UserRole.TEACHER),
            ("substitute", UserRole.TEACHER),
            ("other_teacher", UserRole.TEACHER),
            ("a2", UserRole.STUDENT),
            ("a3", UserRole.STUDENT),
            ("a4", UserRole.STUDENT),
        ):
            user = User(name=key.replace("_", " ").title(), email=f"{key}@example.com", password_hash=hash_password(PASSWORD), role=role)
            users[key] = user
            db.add(user)
        db.flush()
        teachers = {}
        for key in ("teacher", "substitute", "other_teacher"):
            teachers[key] = Teacher(user_id=users[key].id, employee_code=f"T-{key}")
            db.add(teachers[key])
        db.flush()
        students = {}
        for key in ("a2", "a3", "a4"):
            students[key] = Student(user_id=users[key].id, section_id=sections[key.upper()].id, roll_number=f"R-{key.upper()}")
            db.add(students[key])
        db.flush()
        routine = RoutineEntry(
            intake_id=intake.id,
            semester_number=6,
            section_id=sections["A3"].id,
            module_id=module.id,
            class_type_id=class_type.id,
            teacher_id=teachers["teacher"].id,
            room_id=original_room.id,
            day_of_week=date.today().weekday(),
            time_slot_id=slot.id,
        )
        db.add(routine)
        db.flush()
        db.add_all([RoutineEntrySection(routine_entry_id=routine.id, section_id=sections[name].id) for name in ("A3", "A4")])
        db.commit()
        ids = {
            "routine": routine.id,
            "room": original_room.id,
            "override_room": override_room.id,
            "missing_room": missing_room.id,
            **{f"teacher_{key}": value.id for key, value in teachers.items()},
            **{f"student_{key}": value.id for key, value in students.items()},
        }

    client = TestClient(app)

    def headers(key: str):
        response = client.post("/api/v1/auth/login", json={"email": f"{key}@example.com", "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    auth = {key: headers(key) for key in ("teacher", "substitute", "other_teacher", "a2", "a3", "a4")}

    def new_session(
        *,
        routine_id=ids["routine"],
        teacher_id=ids["teacher_teacher"],
        status=SessionStatus.ACTIVE,
        geofence_latitude=ROOM_LATITUDE,
        geofence_longitude=ROOM_LONGITUDE,
        geofence_radius_meters=50,
        teacher_accuracy=10,
    ):
        with TestSession() as db:
            session = ClassSession(
                routine_entry_id=routine_id,
                session_date=date.today(),
                effective_teacher_id=teacher_id,
                effective_room="Machapuchare-L04",
                status=status,
                started_at=datetime.now(UTC),
                geofence_latitude=geofence_latitude,
                geofence_longitude=geofence_longitude,
                geofence_radius_meters=geofence_radius_meters,
                teacher_location_accuracy_meters=teacher_accuracy,
                geofence_captured_at=datetime.now(UTC) if geofence_latitude is not None else None,
            )
            db.add(session)
            db.commit()
            return session.id

    yield client, TestSession, auth, ids, new_session
    app.dependency_overrides.clear()


def get_qr(client, auth, session_id, teacher="teacher"):
    response = client.get(f"/api/v1/sessions/{session_id}/qr", headers=auth[teacher])
    assert response.status_code == 200, response.text
    return response.json()


def scan_check_in(client, auth, token, student="a3", **location):
    payload = {"qr_token": token, "latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy": 8, **location}
    return client.post("/api/v1/check-ins", headers=auth[student], json=payload)


def check_in(client, auth, token, student="a3", **location):
    response = scan_check_in(client, auth, token, student, **location)
    if response.status_code != 200 or response.json().get("status") != "challenge_required":
        return response
    code = get_qr(client, auth, validate_qr_token(token).session_id)["classroom_code"]
    return client.post(
        "/api/v1/check-ins/confirm",
        headers=auth[student],
        json={"verification_token": response.json()["verification_token"], "code": code},
    )


def test_teacher_start_accepts_coarse_campus_location_and_keeps_it_fixed(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    endpoint = f"/api/v1/routine-sessions/{ids['routine']}/start"
    # 1: canonical session creation requires a validated location body.
    assert client.post(endpoint, headers=auth["teacher"]).status_code == 422
    # Ownership is still derived from the authenticated effective teacher.
    assert client.post(endpoint, headers=auth["other_teacher"], json={"latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy_meters": 10}).status_code == 403
    # A +/-69m GPS fix is coarse but is adequate for a campus/audit signal.
    created = client.post(endpoint, headers=auth["teacher"], json={"latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy_meters": 69, "geofence_radius_meters": 150})
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]
    with TestSession() as db:
        # 8: Room coordinates are deliberately absent for normal canonical attendance.
        room = db.get(Room, ids["room"])
        room.latitude = room.longitude = None
        db.commit()
    # The coarse fix, radius, and capture time are stored for audit.
    with TestSession() as db:
        session = db.get(ClassSession, session_id)
        assert session.geofence_latitude == ROOM_LATITUDE and session.geofence_longitude == ROOM_LONGITUDE
        assert session.teacher_location_accuracy_meters == 69
        assert session.geofence_radius_meters == 150
        assert session.geofence_captured_at is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "class_session.started", AuditLog.entity_id == session_id)) is not None
    # 11: pressing Start again cannot silently move the fixed session geofence.
    repeated = client.post(endpoint, headers=auth["teacher"], json={"latitude": 0, "longitude": 0, "accuracy_meters": 1})
    assert repeated.status_code == 200 and repeated.json()["id"] == session_id
    with TestSession() as db:
        session = db.get(ClassSession, session_id)
        assert (session.geofence_latitude, session.geofence_longitude) == (ROOM_LATITUDE, ROOM_LONGITUDE)
    # Room NULL coordinates do not prevent student attendance against the session center.
    token = get_qr(client, auth, session_id)["token"]
    assert check_in(client, auth, token).json()["status"] == "present"


def test_teacher_start_does_not_block_on_low_gps_precision(attendance_env):
    client, _, auth, ids, _ = attendance_env
    response = client.post(
        f"/api/v1/routine-sessions/{ids['routine']}/start",
        headers=auth["teacher"],
        json={"latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy_meters": 5000},
    )
    assert response.status_code == 200, response.text
    assert response.json()["teacher_location_accuracy_meters"] == 5000


def test_teacher_can_configure_checkin_window_and_qr_rotation(attendance_env):
    client, _, auth, ids, _ = attendance_env
    response = client.post(
        f"/api/v1/routine-sessions/{ids['routine']}/start",
        headers=auth["teacher"],
        json={
            "latitude": ROOM_LATITUDE,
            "longitude": ROOM_LONGITUDE,
            "accuracy_meters": 69,
            "self_checkin_window_minutes": 60,
            "challenge_rotation_seconds": 45,
        },
    )
    assert response.status_code == 200, response.text
    session_id = response.json()["id"]
    assert response.json()["self_checkin_window_minutes"] == 60
    assert response.json()["challenge_rotation_seconds"] == 45
    qr = get_qr(client, auth, session_id)
    assert qr["self_checkin_window_minutes"] == 60
    assert qr["rotation_seconds"] == 45


def test_qr_generation_authorization_claims_and_rotation(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    session_id = new_session()
    # 1-3: owner generation, unauthorized teacher, and signed session claims.
    first = get_qr(client, auth, session_id)
    assert first["rotation_seconds"] == settings.attendance_challenge_rotation_seconds
    assert first["classroom_code"].isdigit() and len(first["classroom_code"]) == settings.attendance_code_length
    assert client.get(f"/api/v1/sessions/{session_id}/qr", headers=auth["other_teacher"]).status_code == 403
    claims = validate_qr_token(first["token"])
    assert claims.session_id == session_id and claims.version == 1 and claims.nonce
    # Refreshing inside one generation is idempotent and does not store the raw secret.
    again = get_qr(client, auth, session_id)
    assert again["token"] == first["token"]
    with TestSession() as db:
        session = db.get(ClassSession, session_id)
        assert session.current_qr_token is None
        session.qr_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    second = get_qr(client, auth, session_id)
    assert second["token"] != first["token"] and validate_qr_token(second["token"]).version == 2
    # 6: old rotations fail even while their signed exp claim is still fresh (zero grace).
    old = check_in(client, auth, first["token"])
    assert old.status_code == 400 and old.json()["detail"] == "ATTENDANCE_CHALLENGE_EXPIRED"


def test_expired_modified_cross_session_and_lifecycle_replay(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    first_id, second_id = new_session(), new_session()
    first_qr, second_qr = get_qr(client, auth, first_id), get_qr(client, auth, second_id)
    # 5: a correctly signed but expired dedicated QR is distinguishable.
    expired = jwt.encode(
        {"session_id": first_id, "qr_version": 1, "nonce": "expired", "iat": int((datetime.now(UTC) - timedelta(minutes=2)).timestamp()), "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()), "type": "attendance_qr"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(QRValidationError) as exc:
        validate_qr_token(expired)
    assert exc.value.code == "QR_EXPIRED"
    # 7: signature modification is rejected.
    header, payload, signature = first_qr["token"].split(".")
    signature = ("a" if signature[0] != "a" else "b") + signature[1:]
    modified = ".".join((header, payload, signature))
    response = check_in(client, auth, modified)
    assert response.status_code == 400 and response.json()["detail"] == "INVALID_QR"
    # 8: one session's claims cannot validate as another session's rotation.
    with TestSession() as db, pytest.raises(HTTPException):
        validate_current_rotation(db.get(ClassSession, first_id), validate_qr_token(second_qr["token"]))
    # 9: finalized sessions reject otherwise-current QR.
    with TestSession() as db:
        db.get(ClassSession, first_id).status = SessionStatus.COMPLETED
        db.commit()
    assert check_in(client, auth, first_qr["token"]).json()["detail"] == "SESSION_FINALIZED"
    # Attendance-window closure is also authoritative.
    with TestSession() as db:
        session = db.get(ClassSession, second_id)
        session.started_at = datetime.now(UTC) - timedelta(minutes=settings.attendance_self_checkin_window_minutes + 1)
        db.commit()
    assert check_in(client, auth, second_qr["token"]).json()["detail"] == "SELF_CHECKIN_WINDOW_CLOSED"


def test_cancelled_effective_occurrence_rejects_existing_session(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    session_id = new_session()
    token = get_qr(client, auth, session_id)["token"]
    with TestSession() as db:
        db.add(ScheduleOverride(routine_entry_id=ids["routine"], override_date=date.today(), is_cancelled=True, reason="Cancelled", status=OverrideStatus.APPROVED, created_by=1))
        db.commit()
    # 10: cancellation after session creation invalidates QR generation and check-in.
    assert client.get(f"/api/v1/sessions/{session_id}/qr", headers=auth["teacher"]).json()["detail"] == "SESSION_CANCELLED"
    assert check_in(client, auth, token).json()["detail"] == "SESSION_CANCELLED"


def test_teacher_can_choose_the_session_boundary(attendance_env):
    client, TestSession, auth, ids, _ = attendance_env
    response = client.post(
        f"/api/v1/routine-sessions/{ids['routine']}/start",
        headers=auth["teacher"],
        json={"latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy_meters": 69, "geofence_radius_meters": 150},
    )
    assert response.status_code == 200, response.text
    with TestSession() as db:
        session = db.get(ClassSession, response.json()["id"])
        assert session.geofence_radius_meters == 150


def test_inside_boundary_outside_and_room_specific_radius(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    # 11: room center is accepted.
    session_id = new_session()
    response = check_in(client, auth, get_qr(client, auth, session_id)["token"])
    assert response.status_code == 200 and response.json()["status"] == "present"
    # A point inside the configured campus boundary can proceed to code verification.
    boundary_session = new_session()
    boundary_token = get_qr(client, auth, boundary_session)["token"]
    near_boundary = ROOM_LATITUDE + 20 / 111_195
    response = check_in(client, auth, boundary_token, student="a4", latitude=near_boundary)
    assert response.status_code == 200 and response.json()["status"] == "present"
    # 13: accurate but outside is queued with server-computed evidence.
    outside_session = new_session()
    outside_token = get_qr(client, auth, outside_session)["token"]
    response = check_in(client, auth, outside_token, latitude=ROOM_LATITUDE + 100 / 111_195)
    assert response.status_code == 200 and response.json()["reason"] == "OUTSIDE_GEOFENCE"
    with TestSession() as db:
        attempt = db.scalar(select(CheckInAttempt).where(CheckInAttempt.class_session_id == outside_session))
        assert attempt.distance_meters > 90 and attempt.allowed_radius_meters == 50 and attempt.geofence_pass is False


def test_coarse_geofence_does_not_apply_a_classroom_accuracy_margin(attendance_env):
    client, _, auth, _, new_session = attendance_env
    session_id = new_session(geofence_radius_meters=40, teacher_accuracy=10)
    token = get_qr(client, auth, session_id)["token"]
    response = check_in(client, auth, token, latitude=ROOM_LATITUDE + 23 / 111_195)
    # The student is within the campus boundary. The spoken code supplies the
    # classroom-presence proof, rather than a compounded GPS accuracy margin.
    assert response.status_code == 200 and response.json()["status"] == "present"


@pytest.mark.parametrize("reason", ["LOCATION_DENIED", "LOCATION_TIMEOUT", "LOCATION_UNAVAILABLE"])
def test_structured_browser_location_failures_are_queued(attendance_env, reason):
    client, TestSession, auth, ids, new_session = attendance_env
    session_id = new_session()
    token = get_qr(client, auth, session_id)["token"]
    response = client.post("/api/v1/check-ins", headers=auth["a3"], json={"qr_token": token, "location_failure_reason": reason})
    assert response.status_code == 200 and response.json() == {
        **response.json(),
        "status": "pending_verification",
        "reason": reason,
    }
    with TestSession() as db:
        assert db.scalar(select(CheckInAttempt.failure_reason).where(CheckInAttempt.class_session_id == session_id)) == reason


def test_low_accuracy_historical_missing_center_and_default_radius(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    # 14: poor accuracy never marks Present.
    low_id = new_session()
    low = check_in(client, auth, get_qr(client, auth, low_id)["token"], accuracy=settings.geolocation_max_accuracy_meters + 1)
    assert low.json()["reason"] == "LOW_LOCATION_ACCURACY"
    # Historical canonical sessions without a captured center take a controlled exception path.
    missing_id = new_session(geofence_latitude=None, geofence_longitude=None, geofence_radius_meters=None)
    missing = check_in(client, auth, get_qr(client, auth, missing_id)["token"], student="a4")
    assert missing.json()["reason"] == "SESSION_GEOFENCE_NOT_CONFIGURED"
    # A session center with no configured radius uses the campus default.
    fallback_id = new_session(geofence_radius_meters=None)
    fallback_token = get_qr(client, auth, fallback_id)["token"]
    response = check_in(client, auth, fallback_token, latitude=ROOM_LATITUDE + (settings.geofence_radius_meters + 100) / 111_195)
    assert response.json()["reason"] == "OUTSIDE_GEOFENCE"
    with TestSession() as db:
        attempt = db.scalar(select(CheckInAttempt).where(CheckInAttempt.class_session_id == fallback_id))
        assert attempt.allowed_radius_meters == settings.geofence_radius_meters


def test_effective_override_room_is_display_only_for_session_geofence(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    with TestSession() as db:
        override = ScheduleOverride(
            routine_entry_id=ids["routine"],
            override_date=date.today(),
            new_room="Annapurna",
            reason="Room change",
            status=OverrideStatus.APPROVED,
            created_by=1,
        )
        db.add(override)
        db.commit()
    session_id = new_session()
    qr = get_qr(client, auth, session_id)
    assert qr["room"] == "Annapurna"
    # The override remains display metadata; teacher-captured session center is authoritative.
    assert check_in(client, auth, qr["token"]).json()["status"] == "present"
    second_id = new_session()
    response = check_in(client, auth, get_qr(client, auth, second_id)["token"], student="a4", latitude=27.7200, longitude=85.3300)
    assert response.json()["reason"] == "OUTSIDE_GEOFENCE"


def test_combined_section_eligibility_duplicate_and_identity_spoofing(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    # 21/22: both A3 and A4 are eligible for the one canonical combined class.
    a3_id = new_session()
    a3_token = get_qr(client, auth, a3_id)["token"]
    assert check_in(client, auth, a3_token, student="a3").json()["status"] == "present"
    assert check_in(client, auth, a3_token, student="a4").json()["status"] == "present"
    # 23: A2 is rejected server-side before geofence acceptance.
    invalid_id = new_session()
    invalid_token = get_qr(client, auth, invalid_id)["token"]
    assert check_in(client, auth, invalid_token, student="a2").json()["detail"] == "STUDENT_NOT_ELIGIBLE"
    # 24: duplicate successful check-in is blocked by application and DB uniqueness.
    assert check_in(client, auth, a3_token, student="a3").json()["detail"] == "ALREADY_CHECKED_IN"
    with TestSession() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.class_session_id == a3_id, AttendanceRecord.student_id == ids["student_a3"])) == 1
    # 25: student_id cannot be submitted at all; identity always comes from auth.
    spoof = client.post("/api/v1/check-ins", headers=auth["a3"], json={"qr_token": invalid_token, "latitude": ROOM_LATITUDE, "longitude": ROOM_LONGITUDE, "accuracy": 5, "student_id": ids["student_a4"]})
    assert spoof.status_code == 422


def test_scan_requires_the_teacher_code_before_creating_attendance(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    session_id = new_session()
    qr = get_qr(client, auth, session_id)

    # Students can scan the signed QR but never retrieve the spoken code.
    assert client.get(f"/api/v1/sessions/{session_id}/qr", headers=auth["a3"]).status_code == 403
    scan = scan_check_in(client, auth, qr["token"])
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    assert payload["status"] == "challenge_required"
    assert payload["code_length"] == 5
    assert "code" not in jwt.get_unverified_claims(qr["token"])
    assert "classroom_code" not in payload
    with TestSession() as db:
        assert db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id == session_id)) is None
        assert db.scalar(select(PendingAttendanceVerification).where(PendingAttendanceVerification.class_session_id == session_id)) is not None

    confirmed = client.post(
        "/api/v1/check-ins/confirm",
        headers=auth["a3"],
        json={"verification_token": payload["verification_token"], "code": qr["classroom_code"]},
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "present"
    with TestSession() as db:
        assert db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id == session_id, AttendanceRecord.student_id == ids["student_a3"])) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance.qr_scanned")) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance.challenge_confirmed")) is not None

    replay = client.post(
        "/api/v1/check-ins/confirm",
        headers=auth["a3"],
        json={"verification_token": payload["verification_token"], "code": qr["classroom_code"]},
    )
    assert replay.status_code == 409 and replay.json()["detail"] == "ALREADY_CHECKED_IN"


def test_wrong_code_is_limited_and_teacher_regeneration_invalidates_pending(attendance_env):
    client, TestSession, auth, _, new_session = attendance_env
    session_id = new_session()
    first = get_qr(client, auth, session_id)
    scan = scan_check_in(client, auth, first["token"])
    verification_token = scan.json()["verification_token"]
    wrong_code = "99999" if first["classroom_code"] != "99999" else "00000"

    for remaining in range(settings.attendance_max_code_attempts - 1, 0, -1):
        wrong = client.post(
            "/api/v1/check-ins/confirm",
            headers=auth["a3"],
            json={"verification_token": verification_token, "code": wrong_code},
        )
        assert wrong.status_code == 400 and wrong.json()["detail"] == f"INCORRECT_CLASSROOM_CODE:{remaining}"
    exhausted = client.post(
        "/api/v1/check-ins/confirm",
        headers=auth["a3"],
        json={"verification_token": verification_token, "code": wrong_code},
    )
    assert exhausted.status_code == 400 and exhausted.json()["detail"] == "VERIFICATION_FAILED"
    with TestSession() as db:
        pending = db.scalar(select(PendingAttendanceVerification).where(PendingAttendanceVerification.token_hash.is_not(None)))
        assert pending.failed_attempts == settings.attendance_max_code_attempts
        assert pending.invalidated_at is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance.challenge_failed")) is not None

    second_scan = scan_check_in(client, auth, first["token"], student="a4")
    assert second_scan.status_code == 200
    regenerated = client.post(f"/api/v1/sessions/{session_id}/challenge", headers=auth["teacher"])
    assert regenerated.status_code == 200 and regenerated.json()["token"] != first["token"]
    assert client.post(f"/api/v1/sessions/{session_id}/challenge", headers=auth["other_teacher"]).status_code == 403
    stale_confirm = client.post(
        "/api/v1/check-ins/confirm",
        headers=auth["a4"],
        json={"verification_token": second_scan.json()["verification_token"], "code": first["classroom_code"]},
    )
    assert stale_confirm.status_code == 400 and stale_confirm.json()["detail"] == "ATTENDANCE_CHALLENGE_EXPIRED"
    with TestSession() as db:
        assert db.scalar(select(AttendanceChallenge).where(AttendanceChallenge.class_session_id == session_id, AttendanceChallenge.revoked_at.is_not(None))) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance_challenge.manually_regenerated")) is not None


def test_failed_attempt_rate_limit_and_teacher_exception_decisions(attendance_env):
    client, TestSession, auth, ids, new_session = attendance_env
    session_id = new_session()
    token = get_qr(client, auth, session_id)["token"]
    payload = {"qr_token": token, "location_failure_reason": "LOCATION_DENIED"}
    first = client.post("/api/v1/check-ins", headers=auth["a3"], json=payload)
    second = client.post("/api/v1/check-ins", headers=auth["a3"], json=payload)
    assert first.status_code == second.status_code == 200
    with TestSession() as db:
        assert db.scalar(select(func.count()).select_from(CheckInAttempt).where(CheckInAttempt.class_session_id == session_id)) == 1
    # 26: only an authorized session teacher sees the precise exception evidence.
    queue = client.get(f"/api/v1/sessions/{session_id}/check-in-exceptions", headers=auth["teacher"])
    assert queue.status_code == 200 and queue.json()[0]["reason"] == "LOCATION_DENIED"
    assert client.get(f"/api/v1/sessions/{session_id}/check-in-exceptions", headers=auth["other_teacher"]).status_code == 403
    attempt_id = queue.json()[0]["id"]
    # 27/28: confirmation creates Present and an explicit audit event.
    confirmed = client.patch(f"/api/v1/sessions/{session_id}/check-in-exceptions/{attempt_id}", headers=auth["teacher"], json={"decision": "confirm", "reason": "Student present in room"})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    with TestSession() as db:
        assert db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id == session_id, AttendanceRecord.student_id == ids["student_a3"])) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance.exception_confirmed", AuditLog.entity_id == attempt_id)) is not None
    # 29: a separate pending attempt can be rejected without creating attendance.
    reject_id = new_session()
    reject_token = get_qr(client, auth, reject_id)["token"]
    client.post("/api/v1/check-ins", headers=auth["a4"], json={"qr_token": reject_token, "location_failure_reason": "LOCATION_TIMEOUT"})
    rejected_attempt = client.get(f"/api/v1/sessions/{reject_id}/check-in-exceptions", headers=auth["teacher"]).json()[0]
    rejected = client.patch(f"/api/v1/sessions/{reject_id}/check-in-exceptions/{rejected_attempt['id']}", headers=auth["teacher"], json={"decision": "reject", "reason": "Student was absent"})
    assert rejected.json()["status"] == "rejected"
    # 30: unrelated teachers cannot act on another session's exception.
    forbidden = client.patch(f"/api/v1/sessions/{reject_id}/check-in-exceptions/{rejected_attempt['id']}", headers=auth["other_teacher"], json={"decision": "confirm", "reason": "No"})
    assert forbidden.status_code == 403
