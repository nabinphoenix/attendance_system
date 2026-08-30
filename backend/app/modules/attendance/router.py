import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.dependencies import DbSession, require_role, require_roles
from app.modules.academic.models import RoutineEntry, Section, Student, StudentSubjectEnrollment, Teacher
from app.modules.course_completion.models import CoursePlan
from app.modules.identity.models import User
from app.modules.operations.models import AuditLog
from app.modules.operations.service import log_audit
from app.modules.scheduling.models import ClassSession, OverrideStatus, ScheduleOverride, SessionStatus
from app.modules.scheduling.service import approved_routine_override, resolve_effective_class, resolve_session_schedule, session_section_ids

from .models import (
    AttendanceChange,
    AttendanceChallenge,
    AttendanceMethod,
    AttendanceRecord,
    AttendanceStatus,
    CheckInAttempt,
    CheckInAttemptStatus,
    LeaveRequest,
    PendingAttendanceVerification,
)
from .schemas import (
    CheckInExceptionRead,
    ChallengeConfirmationRequest,
    CheckInRequest,
    CheckInResponse,
    ExceptionDecision,
    QRResponse,
    RosterItem,
    StatusChange,
    TeacherAttendanceClass,
)
from .service import QRClaims, QRValidationError, challenge_is_current, classroom_code_matches, distance_meters, issue_qr_challenge, utc, validate_qr_token, verification_token_digest

router = APIRouter(tags=["attendance"])


def teacher_session(db, user: User, session_id: int) -> ClassSession:
    session = db.get(ClassSession, session_id)
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if not session or not teacher or session.effective_teacher_id != teacher.id:
        raise HTTPException(403, "Not your class session")
    return session


def effective_session(session: ClassSession, db):
    if session.routine_entry_id:
        return resolve_effective_class(db, session.routine_entry, session.session_date)
    return None


def ensure_session_active(session: ClassSession, db) -> None:
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(409, "SESSION_FINALIZED")
    effective = effective_session(session, db)
    if effective and effective.cancelled:
        raise HTTPException(409, "SESSION_CANCELLED")


def ensure_accepting_check_ins(session: ClassSession, db) -> None:
    ensure_session_active(session, db)
    window_minutes = session.self_checkin_window_minutes or settings.attendance_self_checkin_window_minutes
    if utc(session.started_at) + timedelta(minutes=window_minutes) <= datetime.now(UTC):
        raise HTTPException(409, "SELF_CHECKIN_WINDOW_CLOSED")


def session_metadata(session: ClassSession, db) -> tuple[str, list[str], str, object, object]:
    entry = resolve_session_schedule(session)
    if session.routine_entry_id:
        effective = resolve_effective_class(db, entry, session.session_date)
        section_names = list(db.scalars(select(Section.name).where(Section.id.in_(effective.section_ids))).all())
        return entry.module.title, sorted(section_names), effective.room, effective.start_time, effective.end_time
    return entry.subject.name, [entry.section.name], session.effective_room, entry.start_time, entry.end_time


def validate_current_rotation(session: ClassSession, claims: QRClaims) -> None:
    if claims.session_id != session.id or claims.version != session.qr_version or claims.nonce != session.qr_nonce:
        raise HTTPException(400, "ATTENDANCE_CHALLENGE_EXPIRED")


def student_for_user(db, user: User) -> Student:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if not student:
        raise HTTPException(404, "Student profile not found")
    return student


def ensure_student_eligible(session: ClassSession, student: Student, db) -> None:
    entry = resolve_session_schedule(session)
    if session.routine_entry_id:
        if student.section_id not in session_section_ids(session):
            raise HTTPException(403, "STUDENT_NOT_ELIGIBLE")
        return
    enrolled = db.scalar(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_id == student.id,
            StudentSubjectEnrollment.subject_id == entry.subject_id,
        )
    )
    if student.section_id != entry.section_id or not enrolled:
        raise HTTPException(403, "STUDENT_NOT_ELIGIBLE")


def current_challenge(db, session: ClassSession, claims: QRClaims) -> AttendanceChallenge:
    challenge = db.scalar(
        select(AttendanceChallenge).where(
            AttendanceChallenge.class_session_id == session.id,
            AttendanceChallenge.qr_version == claims.version,
            AttendanceChallenge.qr_nonce == claims.nonce,
        )
    )
    if not challenge or not challenge_is_current(session, challenge):
        raise HTTPException(400, "ATTENDANCE_CHALLENGE_EXPIRED")
    return challenge


def pending_attempt(
    db,
    session: ClassSession,
    student: Student,
    claims: QRClaims,
    reason: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    accuracy: float | None = None,
    distance: float | None = None,
    radius: float | None = None,
) -> CheckInAttempt:
    latest = db.scalar(
        select(CheckInAttempt)
        .where(
            CheckInAttempt.class_session_id == session.id,
            CheckInAttempt.student_id == student.id,
            CheckInAttempt.status == CheckInAttemptStatus.PENDING,
            CheckInAttempt.failure_reason == reason,
        )
        .order_by(CheckInAttempt.created_at.desc())
    )
    now = datetime.now(UTC)
    if latest and (now - utc(latest.created_at)).total_seconds() < settings.check_in_attempt_rate_limit_seconds:
        return latest
    attempt = CheckInAttempt(
        class_session_id=session.id,
        student_id=student.id,
        status=CheckInAttemptStatus.PENDING,
        failure_reason=reason,
        qr_version=claims.version,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy,
        distance_meters=distance,
        allowed_radius_meters=radius,
        geofence_pass=False,
    )
    db.add(attempt)
    db.flush()
    return attempt


def pending_response(session: ClassSession, db, reason: str) -> CheckInResponse:
    title, _, room, start, _ = session_metadata(session, db)
    return CheckInResponse(
        status="pending_verification",
        reason=reason,
        module_title=title,
        room=room,
        start_time=start,
        message="Location could not be verified. Your request was sent to the teacher for confirmation.",
    )


def teacher_qr_response(id: int, user: User, db, *, force: bool = False) -> QRResponse:
    session = teacher_session(db, user, id)
    ensure_session_active(session, db)
    # Keep the QR fields and challenge row in the same database transaction.
    session = db.scalar(select(ClassSession).where(ClassSession.id == id).with_for_update())
    token, expires, challenge, code, created = issue_qr_challenge(db, session, user.id, force=force)
    if created:
        now = datetime.now(UTC)
        for pending in db.scalars(
            select(PendingAttendanceVerification).where(
                PendingAttendanceVerification.class_session_id == session.id,
                PendingAttendanceVerification.attendance_challenge_id != challenge.id,
                PendingAttendanceVerification.consumed_at.is_(None),
                PendingAttendanceVerification.invalidated_at.is_(None),
            )
        ).all():
            pending.invalidated_at = now
        action = "attendance_challenge.manually_regenerated" if force else "attendance_challenge.rotated"
        log_audit(
            db,
            user.id,
            action,
            "attendance_challenge",
            challenge.id,
            None,
            {"class_session_id": session.id, "qr_version": challenge.qr_version, "expires_at": expires},
        )
        db.commit()
    title, sections, room, start, end = session_metadata(session, db)
    return QRResponse(
        token=token,
        expires_at=expires,
        rotation_seconds=session.challenge_rotation_seconds or settings.attendance_challenge_rotation_seconds,
        module_title=title,
        section_names=sections,
        room=room,
        start_time=start,
        end_time=end,
        geofence_radius_meters=session.geofence_radius_meters,
        teacher_location_accuracy_meters=session.teacher_location_accuracy_meters,
        self_checkin_window_minutes=session.self_checkin_window_minutes or settings.attendance_self_checkin_window_minutes,
        classroom_code=code,
        challenge_id=challenge.id,
    )


@router.get("/sessions/{id}/qr", response_model=QRResponse)
def qr(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    return teacher_qr_response(id, user, db)


@router.post("/sessions/{id}/challenge", response_model=QRResponse)
def regenerate_challenge(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    return teacher_qr_response(id, user, db, force=True)


@router.post("/check-ins", response_model=CheckInResponse)
def check_in(p: CheckInRequest, user: Annotated[User, Depends(require_role("student"))], db: DbSession):
    """Validate a QR scan and create a single-use pending classroom-code verification."""

    student = student_for_user(db, user)
    try:
        claims = validate_qr_token(p.qr_token)
    except QRValidationError as exc:
        raise HTTPException(400, exc.code) from exc
    session = db.get(ClassSession, claims.session_id)
    if not session:
        raise HTTPException(400, "INVALID_QR")
    ensure_accepting_check_ins(session, db)
    validate_current_rotation(session, claims)
    challenge = current_challenge(db, session, claims)
    ensure_student_eligible(session, student, db)
    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.class_session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if existing:
        raise HTTPException(409, "ALREADY_CHECKED_IN")

    if p.location_failure_reason:
        pending_attempt(db, session, student, claims, p.location_failure_reason)
        log_audit(db, user.id, "attendance.check_in_pending", "class_session", session.id, None, {"reason": p.location_failure_reason})
        db.commit()
        return pending_response(session, db, p.location_failure_reason)
    if p.latitude is None or p.longitude is None or p.accuracy is None:
        raise HTTPException(422, "Location coordinates and accuracy are required")
    if p.accuracy > settings.geolocation_max_accuracy_meters:
        reason = "LOW_LOCATION_ACCURACY"
        pending_attempt(db, session, student, claims, reason, latitude=p.latitude, longitude=p.longitude, accuracy=p.accuracy)
        log_audit(db, user.id, "attendance.check_in_pending", "class_session", session.id, None, {"reason": reason})
        db.commit()
        return pending_response(session, db, reason)

    entry = resolve_session_schedule(session)
    if session.geofence_latitude is not None and session.geofence_longitude is not None:
        center_latitude, center_longitude = session.geofence_latitude, session.geofence_longitude
        radius = session.geofence_radius_meters or settings.geofence_radius_meters
    elif not session.routine_entry_id:
        center_latitude, center_longitude = entry.latitude, entry.longitude
        radius = settings.geofence_radius_meters
    else:
        reason = "SESSION_GEOFENCE_NOT_CONFIGURED"
        pending_attempt(db, session, student, claims, reason, latitude=p.latitude, longitude=p.longitude, accuracy=p.accuracy)
        log_audit(db, user.id, "attendance.check_in_pending", "class_session", session.id, None, {"reason": reason})
        db.commit()
        return pending_response(session, db, reason)
    distance = distance_meters(p.latitude, p.longitude, center_latitude, center_longitude)
    if distance > radius:
        reason = "OUTSIDE_GEOFENCE"
        pending_attempt(db, session, student, claims, reason, latitude=p.latitude, longitude=p.longitude, accuracy=p.accuracy, distance=distance, radius=radius)
        log_audit(db, user.id, "attendance.check_in_pending", "class_session", session.id, None, {"reason": reason, "distance_meters": distance})
        db.commit()
        return pending_response(session, db, reason)

    now = datetime.now(UTC)
    for previous in db.scalars(
        select(PendingAttendanceVerification).where(
            PendingAttendanceVerification.student_id == student.id,
            PendingAttendanceVerification.class_session_id == session.id,
            PendingAttendanceVerification.consumed_at.is_(None),
            PendingAttendanceVerification.invalidated_at.is_(None),
        )
    ).all():
        previous.invalidated_at = now
    verification_token = secrets.token_urlsafe(32)
    verification_expires_at = min(
        utc(challenge.expires_at),
        now + timedelta(seconds=settings.attendance_verification_timeout_seconds),
    )
    verification = PendingAttendanceVerification(
        token_hash=verification_token_digest(verification_token),
        student_id=student.id,
        class_session_id=session.id,
        attendance_challenge_id=challenge.id,
        qr_version=claims.version,
        latitude=p.latitude,
        longitude=p.longitude,
        accuracy_meters=p.accuracy,
        distance_meters=distance,
        allowed_radius_meters=radius,
        created_at=now,
        expires_at=verification_expires_at,
    )
    db.add(verification)
    db.flush()
    log_audit(db, user.id, "attendance.qr_scanned", "pending_attendance_verification", verification.id, None, {"class_session_id": session.id, "challenge_id": challenge.id})
    db.commit()
    title, _, room, start, _ = session_metadata(session, db)
    return CheckInResponse(
        status="challenge_required",
        verification_token=verification_token,
        verification_expires_at=verification_expires_at,
        code_length=settings.attendance_code_length,
        module_title=title,
        room=room,
        start_time=start,
        message=f"QR verified. Enter the {settings.attendance_code_length}-digit code announced by your teacher.",
    )


@router.post("/check-ins/confirm", response_model=CheckInResponse)
def confirm_check_in(p: ChallengeConfirmationRequest, user: Annotated[User, Depends(require_role("student"))], db: DbSession):
    student = student_for_user(db, user)
    pending = db.scalar(
        select(PendingAttendanceVerification)
        .where(PendingAttendanceVerification.token_hash == verification_token_digest(p.verification_token))
        .with_for_update()
    )
    if not pending or pending.student_id != student.id:
        raise HTTPException(400, "VERIFICATION_FAILED")
    if pending.consumed_at is not None:
        raise HTTPException(409, "ALREADY_CHECKED_IN")
    now = datetime.now(UTC)
    session = db.get(ClassSession, pending.class_session_id)
    challenge = db.get(AttendanceChallenge, pending.attendance_challenge_id)
    if (
        pending.invalidated_at is not None
        or utc(pending.expires_at) <= now
        or not session
        or not challenge
        or not challenge_is_current(session, challenge, now)
    ):
        pending.invalidated_at = pending.invalidated_at or now
        db.commit()
        raise HTTPException(400, "ATTENDANCE_CHALLENGE_EXPIRED")
    ensure_accepting_check_ins(session, db)
    ensure_student_eligible(session, student, db)
    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.class_session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if existing:
        pending.consumed_at = now
        db.commit()
        raise HTTPException(409, "ALREADY_CHECKED_IN")
    if len(p.code) != settings.attendance_code_length or not classroom_code_matches(challenge, p.code):
        pending.failed_attempts += 1
        remaining = settings.attendance_max_code_attempts - pending.failed_attempts
        exhausted = remaining <= 0
        if exhausted:
            pending.invalidated_at = now
        log_audit(db, user.id, "attendance.challenge_failed", "pending_attendance_verification", pending.id, None, {"failed_attempts": pending.failed_attempts})
        db.commit()
        if exhausted:
            raise HTTPException(400, "VERIFICATION_FAILED")
        raise HTTPException(400, f"INCORRECT_CLASSROOM_CODE:{remaining}")

    record = AttendanceRecord(
        class_session_id=session.id,
        student_id=student.id,
        status=AttendanceStatus.PRESENT,
        method=AttendanceMethod.QR_GEOFENCE,
        check_in_time=now,
    )
    try:
        db.add(record)
        db.flush()
        pending.consumed_at = now
        db.add(
            CheckInAttempt(
                class_session_id=session.id,
                student_id=student.id,
                status=CheckInAttemptStatus.ACCEPTED,
                qr_version=pending.qr_version,
                latitude=pending.latitude,
                longitude=pending.longitude,
                accuracy_meters=pending.accuracy_meters,
                distance_meters=pending.distance_meters,
                allowed_radius_meters=pending.allowed_radius_meters,
                geofence_pass=True,
            )
        )
        log_audit(db, user.id, "attendance.challenge_confirmed", "attendance_record", record.id, None, {"class_session_id": session.id, "challenge_id": challenge.id, "status": "present"})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "ALREADY_CHECKED_IN") from exc
    db.refresh(record)
    title, _, room_name, start, _ = session_metadata(session, db)
    return CheckInResponse(
        status="present",
        check_in_time=record.check_in_time,
        module_title=title,
        room=room_name,
        start_time=start,
        message="Attendance recorded successfully.",
    )


def session_students(session: ClassSession, db):
    entry = resolve_session_schedule(session)
    if session.routine_entry_id:
        return db.scalars(select(Student).where(Student.section_id.in_(session_section_ids(session)))).all()
    return db.scalars(
        select(Student)
        .join(StudentSubjectEnrollment)
        .where(Student.section_id == entry.section_id, StudentSubjectEnrollment.subject_id == entry.subject_id)
    ).all()


def effective_students(effective, db) -> list[Student]:
    return db.scalars(
        select(Student)
        .where(Student.section_id.in_(effective.section_ids))
        .order_by(Student.roll_number)
    ).all()


def roster_rows_for_students(session_id: int | None, students: list[Student], db) -> list[RosterItem]:
    records = {}
    attempts = {}
    if session_id is not None:
        records = {
            record.student_id: record
            for record in db.scalars(
                select(AttendanceRecord).where(AttendanceRecord.class_session_id == session_id)
            ).all()
        }
        for attempt in db.scalars(
            select(CheckInAttempt)
            .where(
                CheckInAttempt.class_session_id == session_id,
            )
            .order_by(CheckInAttempt.created_at.desc())
        ).all():
            if attempt.student_id not in attempts:
                attempts[attempt.student_id] = attempt
    result = []
    for student in students:
        record = records.get(student.id)
        latest_attempt = attempts.get(student.id)
        attempt_status = latest_attempt.status.value if latest_attempt else "not_checked_in"
        result.append(
            RosterItem(
                attendance_id=record.id if record else None,
                student_id=student.id,
                student_name=student.user.name if student.user else student.name or student.roll_number,
                roll_number=student.roll_number,
                status=record.status.value if record else ("pending_verification" if attempt_status == "pending" else attempt_status),
                check_in_time=record.check_in_time if record else None,
                distance_meters=latest_attempt.distance_meters if latest_attempt else None,
                allowed_radius_meters=latest_attempt.allowed_radius_meters if latest_attempt else None,
                location_accuracy_meters=latest_attempt.accuracy_meters if latest_attempt else None,
            )
        )
    return result


def roster_rows(session: ClassSession, db) -> list[RosterItem]:
    return roster_rows_for_students(session.id, session_students(session, db), db)


def teacher_profile(db, user: User) -> Teacher:
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if not teacher:
        raise HTTPException(404, "Teacher profile not found")
    return teacher


def teacher_routine_occurrence(db, user: User, routine_id: int, attendance_date: date):
    teacher = teacher_profile(db, user)
    entry = db.get(RoutineEntry, routine_id)
    if not entry:
        raise HTTPException(404, "Routine entry not found")
    override = approved_routine_override(db, routine_id, attendance_date)
    if entry.day_of_week != attendance_date.weekday() and not (override and override.is_makeup):
        raise HTTPException(409, "This routine is not scheduled on the selected date")
    effective = resolve_effective_class(db, entry, attendance_date, override)
    if effective.teacher_id != teacher.id:
        raise HTTPException(403, "This class is assigned to another teacher")
    if effective.cancelled:
        raise HTTPException(409, "Class is cancelled")
    return entry, effective


def teacher_attendance_entries(db, teacher_id: int, attendance_date: date) -> list[tuple[RoutineEntry, object]]:
    entries = db.scalars(
        select(RoutineEntry).where(RoutineEntry.day_of_week == attendance_date.weekday())
    ).unique().all()
    makeup_ids = db.scalars(
        select(ScheduleOverride.routine_entry_id).where(
            ScheduleOverride.override_date == attendance_date,
            ScheduleOverride.status == OverrideStatus.APPROVED,
            ScheduleOverride.is_makeup.is_(True),
        )
    ).all()
    if makeup_ids:
        entries.extend(
            db.scalars(select(RoutineEntry).where(RoutineEntry.id.in_(makeup_ids))).unique().all()
        )
    unique_entries = {entry.id: entry for entry in entries}
    result = []
    for entry in unique_entries.values():
        effective = resolve_effective_class(db, entry, attendance_date)
        if effective.teacher_id == teacher_id:
            result.append((entry, effective))
    return sorted(result, key=lambda item: (item[1].start_time, item[0].id))


def manual_session(db, entry: RoutineEntry, effective, attendance_date: date, students: list[Student], user: User) -> ClassSession:
    session = db.scalar(
        select(ClassSession).where(
            ClassSession.routine_entry_id == entry.id,
            ClassSession.session_date == attendance_date,
        )
    )
    today = datetime.now().date()
    now = datetime.now(UTC)
    if not session:
        session = ClassSession(
            routine_entry_id=entry.id,
            session_date=attendance_date,
            effective_teacher_id=effective.teacher_id,
            effective_room=effective.room,
            schedule_override_id=effective.override_id,
            status=SessionStatus.COMPLETED if attendance_date < today else SessionStatus.ACTIVE,
            started_at=now,
            finalized_at=now if attendance_date < today else None,
        )
        db.add(session)
        db.flush()
        log_audit(
            db,
            user.id,
            "class_session.manual_created",
            "class_session",
            session.id,
            None,
            {"routine_entry_id": entry.id, "session_date": attendance_date.isoformat()},
        )
    if attendance_date < today:
        existing_ids = set(
            db.scalars(
                select(AttendanceRecord.student_id).where(AttendanceRecord.class_session_id == session.id)
            ).all()
        )
        for student in students:
            if student.id in existing_ids:
                continue
            leave = db.scalar(
                select(LeaveRequest).where(
                    LeaveRequest.student_id == student.id,
                    LeaveRequest.leave_date == attendance_date,
                    LeaveRequest.status == "approved",
                )
            )
            db.add(
                AttendanceRecord(
                    class_session_id=session.id,
                    student_id=student.id,
                    status=AttendanceStatus.LEAVE if leave else AttendanceStatus.ABSENT,
                    method=AttendanceMethod.FINALIZATION,
                )
            )
        if session.status != SessionStatus.COMPLETED:
            session.status = SessionStatus.COMPLETED
            session.finalized_at = now
            log_audit(db, user.id, "class_session.manual_finalized", "class_session", session.id, {"status": "active"}, {"status": "completed"})
    return session


@router.get("/teacher/attendance", response_model=list[TeacherAttendanceClass])
def teacher_attendance(
    user: Annotated[User, Depends(require_role("teacher"))],
    db: DbSession,
    attendance_date: date = Query(..., alias="date"),
):
    if attendance_date > datetime.now().date():
        raise HTTPException(422, "Manual attendance is available for today and earlier dates only")
    teacher = teacher_profile(db, user)
    result = []
    for entry, effective in teacher_attendance_entries(db, teacher.id, attendance_date):
        session = db.scalar(
            select(ClassSession).where(
                ClassSession.routine_entry_id == entry.id,
                ClassSession.session_date == attendance_date,
            )
        )
        students = effective_students(effective, db)
        section_names = list(db.scalars(select(Section.name).where(Section.id.in_(effective.section_ids))).all())
        result.append(
            TeacherAttendanceClass(
                routine_id=entry.id,
                session_id=session.id if session else None,
                date=attendance_date,
                module_code=entry.module.code,
                module_title=entry.module.title,
                section_names=sorted(section_names),
                start_time=effective.start_time,
                end_time=effective.end_time,
                room=effective.room,
                cancelled=effective.cancelled,
                session_status=session.status.value if session else None,
                students=roster_rows_for_students(session.id if session else None, students, db),
            )
        )
    return result


def apply_manual_status(db, session: ClassSession, student: Student, status: str, reason: str, user: User) -> RosterItem:
    if not reason.strip():
        raise HTTPException(422, "Reason is required")
    try:
        new_status = AttendanceStatus(status.lower())
    except ValueError as exc:
        raise HTTPException(422, "Invalid status") from exc

    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.class_session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if record:
        old_status = record.status
        record.status = new_status
        record.method = AttendanceMethod.MANUAL
        db.add(AttendanceChange(attendance_record_id=record.id, before_status=old_status, after_status=new_status, reason=reason, actor_id=user.id))
        log_audit(db, user.id, "attendance.status_changed", "attendance_record", record.id, {"status": old_status.value}, {"status": new_status.value, "reason": reason})
    else:
        record = AttendanceRecord(class_session_id=session.id, student_id=student.id, status=new_status, method=AttendanceMethod.MANUAL)
        db.add(record)
        db.flush()
        log_audit(db, user.id, "attendance.status_recorded", "attendance_record", record.id, None, {"status": new_status.value, "reason": reason, "class_session_id": session.id})

    pending_status = CheckInAttemptStatus.CONFIRMED if new_status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE) else CheckInAttemptStatus.REJECTED
    for attempt in db.scalars(
        select(CheckInAttempt).where(
            CheckInAttempt.class_session_id == session.id,
            CheckInAttempt.student_id == student.id,
            CheckInAttempt.status == CheckInAttemptStatus.PENDING,
        )
    ).all():
        attempt.status = pending_status
        attempt.reviewed_by = user.id
        attempt.reviewed_at = datetime.now(UTC)
        attempt.decision_reason = reason
    return RosterItem(
        attendance_id=record.id,
        student_id=student.id,
        student_name=student.user.name if student.user else student.name or student.roll_number,
        roll_number=student.roll_number,
        status=record.status.value,
    )


@router.put("/teacher/attendance/{routine_id}/{student_id}", response_model=RosterItem)
def set_teacher_attendance(
    routine_id: int,
    student_id: int,
    p: StatusChange,
    user: Annotated[User, Depends(require_role("teacher"))],
    db: DbSession,
    attendance_date: date = Query(..., alias="date"),
):
    if attendance_date > datetime.now().date():
        raise HTTPException(422, "Manual attendance is available for today and earlier dates only")
    entry, effective = teacher_routine_occurrence(db, user, routine_id, attendance_date)
    students = effective_students(effective, db)
    student = next((item for item in students if item.id == student_id), None)
    if not student:
        raise HTTPException(404, "Student is not enrolled in this class")
    session = manual_session(db, entry, effective, attendance_date, students, user)
    result = apply_manual_status(db, session, student, p.status, p.reason, user)
    db.commit()
    return result


@router.get("/sessions/{id}/attendance", response_model=list[RosterItem])
def roster(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    return roster_rows(teacher_session(db, user, id), db)


@router.get("/sessions/{id}/summary", response_model=list[RosterItem])
def summary(id: int, user: Annotated[User, Depends(require_roles("teacher", "admin"))], db: DbSession):
    session = db.get(ClassSession, id)
    if not session:
        raise HTTPException(404, "Session not found")
    if user.role.value == "teacher":
        teacher_session(db, user, id)
    return roster_rows(session, db)


@router.get("/sessions/{id}/check-in-exceptions", response_model=list[CheckInExceptionRead])
def exceptions(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    teacher_session(db, user, id)
    attempts = db.scalars(
        select(CheckInAttempt)
        .where(
            CheckInAttempt.class_session_id == id,
            CheckInAttempt.status.in_([CheckInAttemptStatus.PENDING, CheckInAttemptStatus.REJECTED]),
        )
        .order_by(CheckInAttempt.created_at)
    ).all()
    result = []
    for attempt in attempts:
        student = db.get(Student, attempt.student_id)
        result.append(
            CheckInExceptionRead(
                id=attempt.id,
                student_name=student.user.name if student.user else student.name or student.roll_number,
                roll_number=student.roll_number,
                section_name=student.section.name,
                reason=attempt.failure_reason or "LOCATION_UNAVAILABLE",
                distance_meters=attempt.distance_meters,
                allowed_radius_meters=attempt.allowed_radius_meters,
                accuracy_meters=attempt.accuracy_meters,
                created_at=attempt.created_at,
                status=attempt.status.value,
            )
        )
    return result


@router.patch("/sessions/{id}/check-in-exceptions/{attempt_id}", response_model=CheckInExceptionRead)
def decide_exception(
    id: int,
    attempt_id: int,
    p: ExceptionDecision,
    user: Annotated[User, Depends(require_role("teacher"))],
    db: DbSession,
):
    teacher_session(db, user, id)
    attempt = db.get(CheckInAttempt, attempt_id)
    if not attempt or attempt.class_session_id != id:
        raise HTTPException(404, "Check-in exception not found")
    if attempt.status != CheckInAttemptStatus.PENDING:
        raise HTTPException(409, "Check-in exception has already been reviewed")
    now = datetime.now(UTC)
    if p.decision == "confirm":
        record = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.class_session_id == id,
                AttendanceRecord.student_id == attempt.student_id,
            )
        )
        if not record:
            record = AttendanceRecord(
                class_session_id=id,
                student_id=attempt.student_id,
                status=AttendanceStatus.PRESENT,
                method=AttendanceMethod.MANUAL,
                check_in_time=now,
            )
            db.add(record)
            db.flush()
        attempt.status = CheckInAttemptStatus.CONFIRMED
        action = "attendance.exception_confirmed"
    else:
        attempt.status = CheckInAttemptStatus.REJECTED
        action = "attendance.exception_rejected"
    attempt.reviewed_by = user.id
    attempt.reviewed_at = now
    attempt.decision_reason = p.reason
    log_audit(db, user.id, action, "check_in_attempt", attempt.id, {"status": "pending"}, {"status": attempt.status.value, "reason": p.reason})
    db.commit()
    db.refresh(attempt)
    student = db.get(Student, attempt.student_id)
    return CheckInExceptionRead(
        id=attempt.id,
        student_name=student.user.name if student.user else student.name or student.roll_number,
        roll_number=student.roll_number,
        section_name=student.section.name,
        reason=attempt.failure_reason or "LOCATION_UNAVAILABLE",
        distance_meters=attempt.distance_meters,
        allowed_radius_meters=attempt.allowed_radius_meters,
        accuracy_meters=attempt.accuracy_meters,
        created_at=attempt.created_at,
        status=attempt.status.value,
    )


@router.post("/sessions/{id}/finalize", response_model=list[RosterItem])
def finalize(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    session = teacher_session(db, user, id)
    entry = resolve_session_schedule(session)
    if session.status == SessionStatus.COMPLETED:
        return roster_rows(session, db)
    pending = db.scalar(
        select(CheckInAttempt.id).where(
            CheckInAttempt.class_session_id == id,
            CheckInAttempt.status == CheckInAttemptStatus.PENDING,
        )
    )
    if pending:
        raise HTTPException(409, "Resolve pending check-in exceptions before finalizing")
    for student in session_students(session, db):
        record = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.class_session_id == id,
                AttendanceRecord.student_id == student.id,
            )
        )
        if not record:
            leave = db.scalar(
                select(LeaveRequest).where(
                    LeaveRequest.student_id == student.id,
                    LeaveRequest.leave_date == session.session_date,
                    LeaveRequest.status == "approved",
                )
            )
            db.add(
                AttendanceRecord(
                    class_session_id=id,
                    student_id=student.id,
                    status=AttendanceStatus.LEAVE if leave else AttendanceStatus.ABSENT,
                    method=AttendanceMethod.FINALIZATION,
                )
            )
    if session.routine_entry_id and entry.module_offering_id:
        plan = db.scalar(
            select(CoursePlan).where(
                CoursePlan.module_offering_id == entry.module_offering_id,
                CoursePlan.batch_id == entry.section.batch_id,
            )
        )
    elif session.routine_entry_id:
        plan = None
    else:
        batch_id = db.scalar(select(Section.batch_id).where(Section.id == entry.section_id))
        plan = db.scalar(select(CoursePlan).where(CoursePlan.subject_id == entry.subject_id, CoursePlan.batch_id == batch_id))
    if plan:
        plan.conducted_sessions += 1
    session.status = SessionStatus.COMPLETED
    session.finalized_at = datetime.now(UTC)
    log_audit(db, user.id, "class_session.finalized", "class_session", session.id, {"status": "active"}, {"status": "completed"})
    db.commit()
    return roster_rows(session, db)


@router.put("/sessions/{id}/attendance/{student_id}", response_model=RosterItem)
def set_session_student_attendance(
    id: int,
    student_id: int,
    p: StatusChange,
    user: Annotated[User, Depends(require_role("teacher"))],
    db: DbSession,
):
    if not p.reason.strip():
        raise HTTPException(422, "Reason is required")
    session = teacher_session(db, user, id)
    student = next((item for item in session_students(session, db) if item.id == student_id), None)
    if not student:
        raise HTTPException(404, "Student is not enrolled in this class session")
    try:
        new_status = AttendanceStatus(p.status.lower())
    except ValueError as exc:
        raise HTTPException(422, "Invalid status") from exc

    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.class_session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if record:
        old_status = record.status
        record.status = new_status
        record.method = AttendanceMethod.MANUAL
        db.add(AttendanceChange(attendance_record_id=record.id, before_status=old_status, after_status=new_status, reason=p.reason, actor_id=user.id))
        log_audit(db, user.id, "attendance.status_changed", "attendance_record", record.id, {"status": old_status.value}, {"status": new_status.value, "reason": p.reason})
    else:
        record = AttendanceRecord(class_session_id=session.id, student_id=student.id, status=new_status, method=AttendanceMethod.MANUAL)
        db.add(record)
        db.flush()
        log_audit(db, user.id, "attendance.status_recorded", "attendance_record", record.id, None, {"status": new_status.value, "reason": p.reason, "class_session_id": session.id})

    pending_status = CheckInAttemptStatus.CONFIRMED if new_status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE) else CheckInAttemptStatus.REJECTED
    for attempt in db.scalars(select(CheckInAttempt).where(CheckInAttempt.class_session_id == session.id, CheckInAttempt.student_id == student.id, CheckInAttempt.status == CheckInAttemptStatus.PENDING)).all():
        attempt.status = pending_status
        attempt.reviewed_by = user.id
        attempt.reviewed_at = datetime.now(UTC)
        attempt.decision_reason = p.reason
    db.commit()
    return RosterItem(attendance_id=record.id, student_id=student.id, student_name=student.user.name if student.user else student.name or student.roll_number, roll_number=student.roll_number, status=record.status.value)


@router.patch("/attendance/{id}", response_model=RosterItem)
def change_status(id: int, p: StatusChange, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    if not p.reason.strip():
        raise HTTPException(422, "Reason is required")
    record = db.get(AttendanceRecord, id)
    if not record:
        raise HTTPException(404, "Attendance record not found")
    teacher_session(db, user, record.class_session_id)
    try:
        new = AttendanceStatus(p.status.lower())
    except ValueError as exc:
        raise HTTPException(422, "Invalid status") from exc
    old = record.status
    db.add(AttendanceChange(attendance_record_id=id, before_status=old, after_status=new, reason=p.reason, actor_id=user.id))
    db.add(AuditLog(actor_id=user.id, action="attendance.status_changed", entity_type="attendance_record", entity_id=id, details=f"{old.value} -> {new.value}: {p.reason}"))
    record.status = new
    record.method = AttendanceMethod.MANUAL
    db.commit()
    student = db.get(Student, record.student_id)
    return RosterItem(attendance_id=record.id, student_id=student.id, student_name=student.user.name, roll_number=student.roll_number, status=record.status.value)
