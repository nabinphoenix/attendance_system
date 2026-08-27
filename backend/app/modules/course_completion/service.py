from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.academic.models import RoutineEntry, Section
from app.modules.course_completion.models import CoursePlan
from app.modules.scheduling.models import ClassSession, ScheduleOverride, TimetableEntry
from app.modules.scheduling.service import resolve_effective_class, session_section_ids


def overlaps(start: time, end: time, other_start: time, other_end: time) -> bool:
    return start < other_end and end > other_start


def session_times(db: Session, session: ClassSession) -> tuple[time, time]:
    if session.routine_entry_id:
        effective = resolve_effective_class(db, session.routine_entry, session.session_date)
        return effective.start_time, effective.end_time
    return session.timetable_entry.start_time, session.timetable_entry.end_time


def session_batch_ids(db: Session, session: ClassSession) -> set[int]:
    if session.routine_entry_id:
        return {
            section.batch_id
            for section_id in session_section_ids(session)
            if (section := db.get(Section, section_id))
        }
    return {session.timetable_entry.section.batch_id}


def find_makeup_slot(db: Session, course_plan_id: int) -> dict | None:
    """Find an additional conflict-free hour for either supported schedule source."""

    plan = db.get(CoursePlan, course_plan_id)
    if not plan:
        return None

    legacy_entry = None
    routine_entry = None
    if plan.module_offering_id:
        routine_entry = db.scalar(
            select(RoutineEntry)
            .where(RoutineEntry.module_offering_id == plan.module_offering_id)
            .order_by(RoutineEntry.id)
        )
        if not routine_entry:
            return None
        candidate_teacher_id = routine_entry.teacher_id
        candidate_room = routine_entry.room.name
        source_filter = ScheduleOverride.routine_entry_id == routine_entry.id
    else:
        legacy_entry = db.scalar(
            select(TimetableEntry)
            .join(Section, TimetableEntry.section_id == Section.id)
            .where(
                TimetableEntry.subject_id == plan.subject_id,
                Section.batch_id == plan.batch_id,
            )
        )
        if not legacy_entry:
            return None
        candidate_teacher_id = legacy_entry.teacher_id
        candidate_room = legacy_entry.room_name
        source_filter = ScheduleOverride.timetable_entry_id == legacy_entry.id

    legacy_entries = db.scalars(select(TimetableEntry)).all()
    routine_entries = db.scalars(select(RoutineEntry)).all()
    sessions = db.scalars(
        select(ClassSession).where(
            ClassSession.session_date.between(date.today(), date.today() + timedelta(days=14))
        )
    ).all()
    rooms = {entry.room_name for entry in legacy_entries} | {entry.room.name for entry in routine_entries} | {session.effective_room for session in sessions}

    for offset in range(15):
        candidate_date = date.today() + timedelta(days=offset)
        if candidate_date.weekday() >= 5:
            continue
        # A routine's normal occurrence is not an additional makeup class.
        if routine_entry and candidate_date.weekday() == routine_entry.day_of_week:
            continue
        if db.scalar(select(ScheduleOverride.id).where(source_filter, ScheduleOverride.override_date == candidate_date)):
            continue
        for hour in range(8, 16):
            start, end = time(hour), time(hour + 1)
            teacher_busy = batch_busy = False
            for entry in legacy_entries:
                if entry.day_of_week == candidate_date.weekday() and overlaps(start, end, entry.start_time, entry.end_time):
                    teacher_busy = teacher_busy or entry.teacher_id == candidate_teacher_id
                    batch_busy = batch_busy or entry.section.batch_id == plan.batch_id
            for entry in routine_entries:
                if entry.day_of_week != candidate_date.weekday():
                    continue
                effective = resolve_effective_class(db, entry, candidate_date)
                if not effective.cancelled and overlaps(start, end, effective.start_time, effective.end_time):
                    teacher_busy = teacher_busy or effective.teacher_id == candidate_teacher_id
                    batch_busy = batch_busy or entry.section.batch_id == plan.batch_id
            for session in sessions:
                if session.session_date != candidate_date:
                    continue
                session_start, session_end = session_times(db, session)
                if overlaps(start, end, session_start, session_end):
                    teacher_busy = teacher_busy or session.effective_teacher_id == candidate_teacher_id
                    batch_busy = batch_busy or plan.batch_id in session_batch_ids(db, session)
            if teacher_busy or batch_busy:
                continue
            for room in sorted(rooms or {candidate_room}):
                room_busy = any(
                    entry.day_of_week == candidate_date.weekday()
                    and entry.room_name == room
                    and overlaps(start, end, entry.start_time, entry.end_time)
                    for entry in legacy_entries
                )
                if not room_busy:
                    for entry in routine_entries:
                        if entry.day_of_week != candidate_date.weekday():
                            continue
                        effective = resolve_effective_class(db, entry, candidate_date)
                        if not effective.cancelled and effective.room == room and overlaps(start, end, effective.start_time, effective.end_time):
                            room_busy = True
                            break
                if not room_busy:
                    room_busy = any(
                        session.session_date == candidate_date
                        and session.effective_room == room
                        and overlaps(start, end, *session_times(db, session))
                        for session in sessions
                    )
                if not room_busy:
                    return {
                        "date": candidate_date,
                        "start_time": start,
                        "room": room,
                        "teacher_id": candidate_teacher_id,
                        "timetable_entry_id": legacy_entry.id if legacy_entry else None,
                        "routine_entry_id": routine_entry.id if routine_entry else None,
                    }
    return None
