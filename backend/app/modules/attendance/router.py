from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.dependencies import DbSession, require_role, require_roles
from app.modules.academic.models import Section, Student, StudentSubjectEnrollment, Teacher
from app.modules.course_completion.models import CoursePlan
from app.modules.identity.models import User
from app.modules.operations.models import AuditLog
from app.modules.operations.service import log_audit
from app.modules.scheduling.models import ClassSession, SessionStatus
from app.modules.scheduling.service import resolve_effective_class, resolve_session_schedule, session_section_ids

from .models import (
    AttendanceChange,
    AttendanceMethod,
    AttendanceRecord,
    AttendanceStatus,
    CheckInAttempt,
    CheckInAttemptStatus,
    LeaveRequest,
)
from .schemas import (
    CheckInExceptionRead,
    CheckInRequest,
    CheckInResponse,
    ExceptionDecision,
    QRResponse,
    RosterItem,
    StatusChange,
)
from .service import QRClaims, QRValidationError, distance_meters, issue_qr_token, utc, validate_qr_token

router = APIRouter(tags=["attendance"])


def teacher_session(db, user: User, session_id: int) -> ClassSession:
    session = db.get(ClassSession, session_id)
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if not session or not teacher:
        raise HTTPException(403, "Not your class session")
    allowed = {session.effective_teacher_id}
    if session.routine_entry_id and session.routine_entry:
        allowed.add(session.routine_entry.teacher_id)
        allowed.add(resolve_effective_class(db, session.routine_entry, session.session_date).teacher_id)
    elif session.timetable_entry:
        allowed.add(session.timetable_entry.teacher_id)
    if teacher.id not in allowed:
        raise HTTPException(403, "Not your class session")
    return session


def effective_session(session: ClassSession, db):
    if session.routine_entry_id:
        return resolve_effective_class(db, session.routine_entry, session.session_date)
    return None


def ensure_accepting_check_ins(session: ClassSession, db) -> None:
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(409, "SESSION_FINALIZED")
    effective = effective_session(session, db)
    if effective and effective.cancelled:
        raise HTTPException(409, "SESSION_CANCELLED")
    if utc(session.started_at) + timedelta(minutes=settings.attendance_window_minutes) <= datetime.now(UTC):
        raise HTTPException(409, "ATTENDANCE_WINDOW_CLOSED")


def session_metadata(session: ClassSession, db) -> tuple[str, list[str], str, object, object]:
    entry = resolve_session_schedule(session)
    if session.routine_entry_id:
        effective = resolve_effective_class(db, entry, session.session_date)
        section_names = list(db.scalars(select(Section.name).where(Section.id.in_(effective.section_ids))).all())
        return entry.module.title, sorted(section_names), effective.room, effective.start_time, effective.end_time
    return entry.subject.name, [entry.section.name], session.effective_room, entry.start_time, entry.end_time


def validate_current_rotation(session: ClassSession, claims: QRClaims) -> None:
    if claims.session_id != session.id or claims.version != session.qr_version or claims.nonce != session.qr_nonce:
        raise HTTPException(400, "INVALID_QR")


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


@router.get("/sessions/{id}/qr", response_model=QRResponse)
def qr(id: int, user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    session = teacher_session(db, user, id)
    ensure_accepting_check_ins(session, db)
    # Serialize generation changes so simultaneous refreshes cannot publish two nonces.
    session = db.scalar(select(ClassSession).where(ClassSession.id == id).with_for_update())
    token, expires, created = issue_qr_token(session)
    if created:
        log_audit(
            db,
            user.id,
            "attendance_qr.issued",
            "class_session",
            session.id,
            None,
            {"qr_version": session.qr_version, "expires_at": expires},
        )
        db.commit()
    title, sections, room, start, end = session_metadata(session, db)
    return QRResponse(
        token=token,
        expires_at=expires,
        rotation_seconds=settings.qr_token_expire_seconds,
        module_title=title,
        section_names=sections,
        room=room,
        start_time=start,
        end_time=end,
        geofence_radius_meters=session.geofence_radius_meters,
        teacher_location_accuracy_meters=session.teacher_location_accuracy_meters,
    )


@router.post("/check-ins", response_model=CheckInResponse)
def check_in(p: CheckInRequest, user: Annotated[User, Depends(require_role("student"))], db: DbSession):
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if not student:
        raise HTTPException(404, "Student profile not found")
    try:
        claims = validate_qr_token(p.qr_token)
    except QRValidationError as exc:
        raise HTTPException(400, exc.code) from exc
    session = db.get(ClassSession, claims.session_id)
    if not session:
        raise HTTPException(400, "INVALID_QR")
    ensure_accepting_check_ins(session, db)
    validate_current_rotation(session, claims)
    entry = resolve_session_schedule(session)
    if session.routine_entry_id:
        if student.section_id not in session_section_ids(session):
            raise HTTPException(403, "STUDENT_NOT_ELIGIBLE")
    else:
        enrolled = db.scalar(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_id == student.id,
                StudentSubjectEnrollment.subject_id == entry.subject_id,
            )
        )
        if student.section_id != entry.section_id or not enrolled:
            raise HTTPException(403, "STUDENT_NOT_ELIGIBLE")
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

    if session.geofence_latitude is not None and session.geofence_longitude is not None:
        center_latitude, center_longitude = session.geofence_latitude, session.geofence_longitude
        radius = session.geofence_radius_meters or settings.geofence_radius_meters
    elif not session.routine_entry_id:
        # Historical legacy sessions retain their original timetable-coordinate behavior.
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
        pending_attempt(
            db,
            session,
            student,
            claims,
            reason,
            latitude=p.latitude,
            longitude=p.longitude,
            accuracy=p.accuracy,
            distance=distance,
            radius=radius,
        )
        log_audit(db, user.id, "attendance.check_in_pending", "class_session", session.id, None, {"reason": reason})
        db.commit()
        return pending_response(session, db, reason)

    record = AttendanceRecord(
        class_session_id=session.id,
        student_id=student.id,
        status=AttendanceStatus.PRESENT,
        method=AttendanceMethod.QR_GEOFENCE,
        check_in_time=datetime.now(UTC),
    )
    try:
        db.add(record)
        db.flush()
        db.add(
            CheckInAttempt(
                class_session_id=session.id,
                student_id=student.id,
                status=CheckInAttemptStatus.ACCEPTED,
                qr_version=claims.version,
                latitude=p.latitude,
                longitude=p.longitude,
                accuracy_meters=p.accuracy,
                distance_meters=distance,
                allowed_radius_meters=radius,
                geofence_pass=True,
            )
        )
        log_audit(db, user.id, "attendance.check_in", "attendance_record", record.id, None, {"class_session_id": session.id, "status": "present"})
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
        message="Attendance recorded",
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


def roster_rows(session: ClassSession, db) -> list[RosterItem]:
    result = []
    for student in session_students(session, db):
        record = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.class_session_id == session.id,
                AttendanceRecord.student_id == student.id,
            )
        )
        latest_attempt = db.scalar(
            select(CheckInAttempt).where(
                CheckInAttempt.class_session_id == session.id,
                CheckInAttempt.student_id == student.id,
                CheckInAttempt.status.in_([CheckInAttemptStatus.PENDING, CheckInAttemptStatus.REJECTED]),
            ).order_by(CheckInAttempt.created_at.desc())
        )
        attempt_status = latest_attempt.status.value if latest_attempt else "not_checked_in"
        result.append(
            RosterItem(
                attendance_id=record.id if record else None,
                student_id=student.id,
                student_name=student.user.name if student.user else student.name or student.roll_number,
                roll_number=student.roll_number,
                status=record.status.value if record else ("pending_verification" if attempt_status == "pending" else attempt_status),
            )
        )
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
