from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.academic.models import AcademicModule, ClassType, RoutineEntry, Student, Subject
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
PASSING=(AttendanceStatus.PRESENT,AttendanceStatus.LATE)
def subject_stats(db:Session,student_id:int)->list[dict]:
    """Return attendance by legacy subject or canonical academic module."""
    rows=db.execute(
        select(
            AttendanceRecord.status,
            TimetableEntry.subject_id,
            Subject.name,
            Subject.code,
            RoutineEntry.module_id,
            AcademicModule.title,
            AcademicModule.code,
            ClassType.name,
            TimetableEntry.class_type,
        )
        .join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id)
        .outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id)
        .outerjoin(Subject,TimetableEntry.subject_id==Subject.id)
        .outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id)
        .outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id)
        .outerjoin(ClassType,RoutineEntry.class_type_id==ClassType.id)
        .where(AttendanceRecord.student_id==student_id,ClassSession.status==SessionStatus.COMPLETED)
    ).all();groups={}
    for status,subject_id,subject_name,subject_code,module_id,module_title,module_code,class_type_name,legacy_class_type in rows:
        scope_type,scope_id,name,code=("MODULE",module_id,module_title,module_code) if module_id else ("SUBJECT",subject_id,subject_name,subject_code)
        g=groups.setdefault((scope_type,scope_id),{"subject_id":scope_id,"subject_name":name,"subject_code":code,"scope_type":scope_type,"scope_id":scope_id,"present":0,"absent":0,"total":0,"class_types":set()});g["total"]+=1
        if class_type_name or legacy_class_type:g["class_types"].add(class_type_name or legacy_class_type)
        if status in PASSING:g["present"]+=1
        else:g["absent"]+=1
    for g in groups.values():
        g["percentage"]=round(100*g["present"]/g["total"],2) if g["total"] else 0
        g["class_types"]=sorted(g["class_types"])
    return list(groups.values())


def attendance_alert_content(student, stat: dict) -> tuple[str, str, str]:
    """Build a subject-specific warning from the canonical evaluation result."""
    from app.modules.operations.email_templates import attendance_alert_email as build_attendance_alert_email

    name = student.user.name if student.user else student.name or student.roll_number
    return build_attendance_alert_email(
        student_name=name,
        module_name=stat["subject_name"] or "Your scheduled module",
        module_code=stat.get("subject_code"),
        class_types=stat.get("class_types") or [],
        percentage=stat["percentage"],
        threshold=settings.attendance_threshold_percent,
        attended_sessions=stat["present"],
        eligible_sessions=stat["total"],
        semester_label=stat.get("semester_label"),
    )


def attendance_alert_body(student, stat: dict) -> str:
    return attendance_alert_content(student, stat)[1]


def _attendance_scope_for_session(db: Session, session: ClassSession, student: Student) -> dict | None:
    """Return the one academic scope a session may contribute to for a student."""
    from app.modules.academic.models import (
        AcademicModule,
        CohortSemester,
        ModuleOffering,
        RoutineEntry,
        RoutineEntrySection,
        Section,
        Subject,
    )
    from app.modules.academic.promotion_service import student_section_at

    if session.routine_entry_id is not None:
        routine = db.get(RoutineEntry, session.routine_entry_id)
        if routine is None or routine.module_offering_id is None:
            # Canonical sessions without a valid offering are intentionally not
            # eligible for automatic alerts because their academic context is
            # ambiguous.
            return None
        offering = db.get(ModuleOffering, routine.module_offering_id)
        module = db.get(AcademicModule, routine.module_id)
        if offering is None or module is None:
            return None

        section_ids = {routine.section_id}
        section_ids.update(
            db.scalars(
                select(RoutineEntrySection.section_id).where(
                    RoutineEntrySection.routine_entry_id == routine.id
                )
            ).all()
        )
        if student_section_at(db, student.id, session.session_date) not in section_ids:
            return None
        batch_ids = set(
            db.scalars(select(Section.batch_id).where(Section.id.in_(section_ids))).all()
        )
        if (
            len(batch_ids) != 1
            or offering.batch_id not in batch_ids
            or offering.intake_id != routine.intake_id
            or offering.academic_module_id != routine.module_id
        ):
            return None

        cohort_semester_id = offering.cohort_semester_id or routine.cohort_semester_id
        if (
            offering.cohort_semester_id is not None
            and routine.cohort_semester_id is not None
            and offering.cohort_semester_id != routine.cohort_semester_id
        ):
            return None
        cohort = db.get(CohortSemester, cohort_semester_id) if cohort_semester_id else None
        if cohort and not (cohort.start_date <= session.session_date <= cohort.end_date):
            return None
        return {
            "key": ("MODULE_OFFERING", offering.id),
            "module_offering_id": offering.id,
            "subject_id": None,
            "cohort_semester_id": cohort_semester_id,
            "subject_name": module.title,
            "subject_code": module.code,
            "semester_label": f"Semester {offering.semester_number}",
            "case_scope_type": "MODULE",
            "case_scope_id": module.id,
        }

    if session.timetable_entry_id is not None:
        entry = db.get(TimetableEntry, session.timetable_entry_id)
        if entry is None or student_section_at(db, student.id, session.session_date) != entry.section_id:
            return None
        subject = db.get(Subject, entry.subject_id)
        if subject is None:
            return None
        return {
            "key": ("SUBJECT", subject.id),
            "module_offering_id": None,
            "subject_id": subject.id,
            "cohort_semester_id": None,
            "subject_name": subject.name,
            "subject_code": subject.code,
            "semester_label": None,
            "case_scope_type": "SUBJECT",
            "case_scope_id": subject.id,
        }
    return None


def _scope_is_current(db: Session, scope: dict) -> bool:
    """Normal attendance events only alert for an active current offering."""
    if scope["module_offering_id"] is None:
        return True
    from datetime import date
    from app.modules.academic.models import CohortSemester, ModuleOffering

    offering = db.get(ModuleOffering, scope["module_offering_id"])
    if offering is None or not offering.is_active:
        return False
    if scope["cohort_semester_id"] is None:
        return True
    cohort = db.get(CohortSemester, scope["cohort_semester_id"])
    return cohort is not None and cohort.start_date <= date.today() <= cohort.end_date


def _scope_stats(db: Session, student_id: int, scope: dict) -> dict:
    """Use the same finalized records and passing statuses as attendance reports."""
    from app.modules.academic.models import ClassType, RoutineEntry
    rows = db.execute(
        select(AttendanceRecord.status, ClassType.name, TimetableEntry.class_type)
        .join(ClassSession, AttendanceRecord.class_session_id == ClassSession.id)
        .outerjoin(RoutineEntry, ClassSession.routine_entry_id == RoutineEntry.id)
        .outerjoin(ClassType, RoutineEntry.class_type_id == ClassType.id)
        .outerjoin(TimetableEntry, ClassSession.timetable_entry_id == TimetableEntry.id)
        .where(
            AttendanceRecord.student_id == student_id,
            ClassSession.status == SessionStatus.COMPLETED,
            RoutineEntry.module_offering_id == scope["module_offering_id"]
            if scope["module_offering_id"] is not None
            else TimetableEntry.subject_id == scope["subject_id"],
        )
    ).all()
    present = sum(status in PASSING for status, _, _ in rows)
    total = len(rows)
    return {
        **scope,
        "present": present,
        "absent": total - present,
        "total": total,
        "percentage": round(100 * present / total, 2) if total else 0,
        "class_types": sorted(
            {class_type_name or legacy_class_type for _, class_type_name, legacy_class_type in rows if class_type_name or legacy_class_type}
        ),
    }


def _active_threshold_alert(db: Session, student_id: int, scope: dict):
    from app.modules.crm.models import AttendanceThresholdAlert, AttendanceThresholdAlertStatus

    query = select(AttendanceThresholdAlert).where(
        AttendanceThresholdAlert.student_id == student_id,
        AttendanceThresholdAlert.status == AttendanceThresholdAlertStatus.ACTIVE,
    )
    if scope["module_offering_id"] is not None:
        query = query.where(
            AttendanceThresholdAlert.module_offering_id == scope["module_offering_id"]
        )
    else:
        query = query.where(AttendanceThresholdAlert.subject_id == scope["subject_id"])
    return db.scalar(query)


def _audit_threshold_event(
    db: Session,
    actor_id: int | None,
    action: str,
    alert_id: int,
    college_id: int,
    details: dict,
) -> None:
    if actor_id is None:
        return
    from app.modules.operations.service import log_audit

    log_audit(
        db,
        actor_id,
        action,
        "attendance_threshold_alert",
        alert_id,
        None,
        details,
        college_id=college_id,
    )


def _resolve_attendance_case(db: Session, student_id: int, scope: dict, now) -> None:
    """Keep the existing support-case UI in step with a recovered alert."""
    from app.modules.crm.models import CaseStatus, StudentCase

    case = db.scalar(
        select(StudentCase).where(
            StudentCase.student_id == student_id,
            StudentCase.trigger_type == "ATTENDANCE_LOW",
            StudentCase.scope_type == scope["case_scope_type"],
            StudentCase.scope_id == scope["case_scope_id"],
            StudentCase.status.in_([CaseStatus.OPEN, CaseStatus.IN_PROGRESS]),
        )
    )
    if case is not None:
        case.status = CaseStatus.RESOLVED
        case.closed_at = now
        case.last_evaluated_at = now


def _queue_threshold_email(
    db: Session,
    alert,
    student: Student,
    stat: dict,
    actor_id: int | None,
    now,
) -> None:
    from app.modules.operations.service import queue_notification

    subject, body, html_body = attendance_alert_content(student, stat)
    notification = queue_notification(
        db,
        "student",
        student.id,
        subject,
        body,
        "attendance_threshold_alert",
        alert.id,
        html_body=html_body,
        actor_id=actor_id,
        college_id=student.college_id,
    )
    db.flush()
    alert.notification_id = notification.id
    alert.email_queued_at = now
    _audit_threshold_event(
        db,
        actor_id,
        "attendance_threshold.email_queued",
        alert.id,
        student.college_id,
        {"notification_id": notification.id, "percentage": stat["percentage"]},
    )


def _evaluate_scope(
    db: Session,
    student: Student,
    scope: dict,
    *,
    actor_id: int | None,
    send_alerts: bool,
) -> dict:
    from datetime import UTC, datetime
    from app.modules.crm.models import (
        AttendanceThresholdAlert,
        AttendanceThresholdAlertStatus,
    )
    from app.modules.crm.service import get_or_create_attendance_case

    now = datetime.now(UTC)
    stat = _scope_stats(db, student.id, scope)
    alert = _active_threshold_alert(db, student.id, scope)
    result = {"evaluated": 1, "triggered": 0, "created": 0, "updated": 0, "resolved": 0}

    below_threshold = (
        stat["total"] >= settings.minimum_observations
        and stat["percentage"] < settings.attendance_threshold_percent
    )
    if below_threshold:
        result["triggered"] = 1
        if alert is None:
            alert = AttendanceThresholdAlert(
                student_id=student.id,
                module_offering_id=scope["module_offering_id"],
                subject_id=scope["subject_id"],
                cohort_semester_id=scope["cohort_semester_id"],
                threshold=settings.attendance_threshold_percent,
                percentage_at_trigger=stat["percentage"],
                attended_sessions=stat["present"],
                eligible_sessions=stat["total"],
                status=AttendanceThresholdAlertStatus.ACTIVE,
                college_id=student.college_id,
            )
            db.add(alert)
            db.flush()
            _, case_created = get_or_create_attendance_case(
                db,
                student.id,
                scope["case_scope_type"],
                scope["case_scope_id"],
                stat["percentage"],
            )
            result["created"] = int(case_created)
            _audit_threshold_event(
                db,
                actor_id,
                "attendance_threshold.crossed",
                alert.id,
                student.college_id,
                {
                    "student_id": student.id,
                    "module_offering_id": scope["module_offering_id"],
                    "subject_id": scope["subject_id"],
                    "cohort_semester_id": scope["cohort_semester_id"],
                    "percentage": stat["percentage"],
                    "threshold": settings.attendance_threshold_percent,
                },
            )
        else:
            alert.last_evaluated_at = now
            result["updated"] = 1

        # A state-only backfill has no notification_id.  It becomes deliverable
        # only when an administrator explicitly requests alerts in a batch run.
        if send_alerts and alert.notification_id is None:
            _queue_threshold_email(db, alert, student, stat, actor_id, now)
        return result

    if alert is not None and stat["percentage"] >= settings.attendance_threshold_percent:
        alert.status = AttendanceThresholdAlertStatus.RESOLVED
        alert.resolved_at = now
        alert.last_evaluated_at = now
        _resolve_attendance_case(db, student.id, scope, now)
        result["resolved"] = 1
        _audit_threshold_event(
            db,
            actor_id,
            "attendance_threshold.resolved",
            alert.id,
            student.college_id,
            {
                "student_id": student.id,
                "percentage": stat["percentage"],
                "threshold": settings.attendance_threshold_percent,
            },
        )
    return result


def _add_evaluation_totals(totals: dict, result: dict) -> None:
    for key in totals:
        totals[key] += result.get(key, 0)


def evaluate_saved_session(
    db: Session,
    session_id: int,
    *,
    actor_id: int | None = None,
    send_alerts: bool = True,
) -> dict:
    """Evaluate only the students and offering changed by one completed session."""
    session = db.get(ClassSession, session_id)
    totals = {"evaluated": 0, "triggered": 0, "created": 0, "updated": 0, "resolved": 0}
    if session is None or session.status != SessionStatus.COMPLETED:
        return totals

    for student in db.scalars(
        select(Student)
        .join(AttendanceRecord, AttendanceRecord.student_id == Student.id)
        .where(AttendanceRecord.class_session_id == session.id)
    ).all():
        scope = _attendance_scope_for_session(db, session, student)
        if scope is None or not _scope_is_current(db, scope):
            continue
        _add_evaluation_totals(
            totals,
            _evaluate_scope(
                db,
                student,
                scope,
                actor_id=actor_id,
                send_alerts=send_alerts,
            ),
        )
    db.commit()
    return totals


def safely_evaluate_saved_session(
    db: Session,
    session_id: int,
    *,
    actor_id: int | None = None,
    send_alerts: bool = True,
) -> dict:
    """Never let downstream alert persistence change an already saved class."""
    import logging

    try:
        return evaluate_saved_session(
            db,
            session_id,
            actor_id=actor_id,
            send_alerts=send_alerts,
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Attendance threshold evaluation failed after class session %s was saved",
            session_id,
        )
        return {"evaluated": 0, "triggered": 0, "created": 0, "updated": 0, "resolved": 0}


def _student_scopes(db: Session, student: Student) -> list[dict]:
    sessions = db.scalars(
        select(ClassSession)
        .join(AttendanceRecord, AttendanceRecord.class_session_id == ClassSession.id)
        .where(
            AttendanceRecord.student_id == student.id,
            ClassSession.status == SessionStatus.COMPLETED,
        )
        .order_by(ClassSession.session_date.desc(), ClassSession.id.desc())
    ).all()
    scopes: dict[tuple[str, int], dict] = {}
    for session in sessions:
        scope = _attendance_scope_for_session(db, session, student)
        if scope is not None:
            scopes.setdefault(scope["key"], scope)
    return list(scopes.values())


def run_risk_evaluations(
    db: Session,
    *,
    actor_id: int | None = None,
    student_id: int | None = None,
    module_offering_id: int | None = None,
    batch_id: int | None = None,
    send_alerts: bool = False,
    current_only: bool = True,
) -> dict:
    """Shared real-time and bulk recalculation entry point.

    Its safe default records current conditions without emailing historical
    students.  Passing send_alerts=True is the explicit backfill action.
    """
    from app.modules.academic.models import ModuleOffering

    totals = {"evaluated": 0, "triggered": 0, "created": 0, "updated": 0, "resolved": 0}
    students = db.scalars(
        select(Student).where(Student.id == student_id) if student_id is not None else select(Student)
    ).all()
    for student in students:
        for scope in _student_scopes(db, student):
            if module_offering_id is not None and scope["module_offering_id"] != module_offering_id:
                continue
            if batch_id is not None:
                if scope["module_offering_id"] is None:
                    continue
                offering = db.get(ModuleOffering, scope["module_offering_id"])
                if offering is None or offering.batch_id != batch_id:
                    continue
            if current_only and not _scope_is_current(db, scope):
                continue
            _add_evaluation_totals(
                totals,
                _evaluate_scope(
                    db,
                    student,
                    scope,
                    actor_id=actor_id,
                    send_alerts=send_alerts,
                ),
            )
    db.commit()
    return totals
