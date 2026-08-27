from dataclasses import dataclass
from datetime import date, time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.academic.models import RoutineEntry, RoutineEntrySection, Section, Teacher
from app.modules.scheduling.models import OverrideStatus, ScheduleOverride


@dataclass(frozen=True)
class EffectiveClass:
    routine_entry: RoutineEntry
    date: date
    start_time: time
    end_time: time
    teacher_id: int
    room: str
    section_ids: frozenset[int]
    module_id: int
    class_type_id: int
    cancelled: bool
    override_id: int | None


def create_schedule_override(db:Session,*,override_date:date,created_by:int,reason:str,timetable_entry_id:int|None=None,routine_entry_id:int|None=None,new_teacher_id:int|None=None,new_room:str|None=None,start_time:time|None=None,end_time:time|None=None,is_cancelled:bool=False,is_makeup:bool=False,status:OverrideStatus=OverrideStatus.PENDING)->ScheduleOverride:
    if bool(timetable_entry_id) == bool(routine_entry_id):raise ValueError("Provide exactly one schedule source")
    obj=ScheduleOverride(timetable_entry_id=timetable_entry_id,routine_entry_id=routine_entry_id,override_date=override_date,created_by=created_by,reason=reason,new_teacher_id=new_teacher_id,new_room=new_room,start_time=start_time,end_time=end_time,is_cancelled=is_cancelled,is_makeup=is_makeup,status=status);db.add(obj);db.flush();return obj


def routine_section_ids(db: Session, entry: RoutineEntry) -> frozenset[int]:
    linked = frozenset(db.scalars(select(RoutineEntrySection.section_id).where(RoutineEntrySection.routine_entry_id == entry.id)))
    return linked or frozenset({entry.section_id})


def approved_routine_override(db: Session, routine_id: int, on_date: date) -> ScheduleOverride | None:
    return db.scalar(
        select(ScheduleOverride).where(
            ScheduleOverride.routine_entry_id == routine_id,
            ScheduleOverride.override_date == on_date,
            ScheduleOverride.status == OverrideStatus.APPROVED,
        )
    )


def resolve_effective_class(
    db: Session,
    entry: RoutineEntry,
    on_date: date,
    override: ScheduleOverride | None = None,
) -> EffectiveClass:
    """Resolve one canonical routine occurrence and its approved/proposed override."""

    override = override if override is not None else approved_routine_override(db, entry.id, on_date)
    start = override.start_time if override and override.start_time is not None else entry.time_slot.start_time
    end = override.end_time if override and override.end_time is not None else entry.time_slot.end_time
    return EffectiveClass(
        routine_entry=entry,
        date=on_date,
        start_time=start,
        end_time=end,
        teacher_id=override.new_teacher_id if override and override.new_teacher_id is not None else entry.teacher_id,
        room=override.new_room if override and override.new_room else entry.room.name,
        section_ids=routine_section_ids(db, entry),
        module_id=entry.module_id,
        class_type_id=entry.class_type_id,
        cancelled=bool(override and override.is_cancelled),
        override_id=override.id if override else None,
    )


def times_overlap(first_start: time, first_end: time, second_start: time, second_end: time) -> bool:
    return first_start < second_end and first_end > second_start


def routine_override_conflicts(db: Session, entry: RoutineEntry, proposed: ScheduleOverride) -> tuple[EffectiveClass, list[dict]]:
    if not proposed.is_makeup and proposed.override_date.weekday() != entry.day_of_week:
        raise HTTPException(422, "Override date must fall on the routine's scheduled day")
    candidate = resolve_effective_class(db, entry, proposed.override_date, proposed)
    if candidate.start_time >= candidate.end_time:
        raise HTTPException(422, "Override end time must be after start time")
    if candidate.cancelled:
        return candidate, []

    conflicts = []
    others = db.scalars(
        select(RoutineEntry).where(
            RoutineEntry.day_of_week == proposed.override_date.weekday(),
            RoutineEntry.id != entry.id,
        )
    ).all()
    for other_entry in others:
        other = resolve_effective_class(db, other_entry, proposed.override_date)
        if other.cancelled or not times_overlap(candidate.start_time, candidate.end_time, other.start_time, other.end_time):
            continue
        interval = f"{other.start_time:%H:%M} to {other.end_time:%H:%M}"
        teacher = db.get(Teacher, other.teacher_id)
        teacher_name = teacher.user.name if teacher else "the assigned lecturer"
        section_names = [item.name for item in db.scalars(select(Section).where(Section.id.in_(other.section_ids))).all()]
        class_label = f"{other_entry.module.code} - {other_entry.module.title} ({other_entry.class_type.name})"
        common = {"routine_id": other_entry.id, "class_label": class_label, "teacher_name": teacher_name, "room_name": other.room, "section_names": section_names, "time_range": interval}
        if candidate.room.casefold() == other.room.casefold():
            conflicts.append({"resource":"room", "title":"Room conflict", "description":f"{other.room} is occupied by {teacher_name}'s {class_label} class for {' + '.join(section_names)}, {proposed.override_date} {interval}.", **common})
        if candidate.teacher_id == other.teacher_id:
            conflicts.append({"resource":"teacher", "title":"Teacher conflict", "description":f"{teacher_name} already teaches {class_label} for {' + '.join(section_names)} in {other.room}, {proposed.override_date} {interval}.", **common})
        overlap = candidate.section_ids & other.section_ids
        if overlap:
            shared_names = [item.name for item in db.scalars(select(Section).where(Section.id.in_(overlap))).all()]
            conflicts.append({"resource":"section", "title":"Section conflict", "description":f"{' + '.join(shared_names)} already has {class_label} with {teacher_name} in {other.room}, {proposed.override_date} {interval}.", **common})
    return candidate, conflicts


def validate_routine_override_conflicts(db: Session, entry: RoutineEntry, proposed: ScheduleOverride) -> EffectiveClass:
    candidate, conflicts = routine_override_conflicts(db, entry, proposed)
    if conflicts:
        raise HTTPException(409, f"{conflicts[0]['title']}: {conflicts[0]['description']}")
    return candidate


def resolve_session_schedule(session):
    """Compatibility reader: routine for new sessions, legacy timetable only for history."""
    return session.routine_entry or session.timetable_entry


def session_section_ids(session)->set[int]:
    if session.routine_entry:return {x.section_id for x in session.routine_entry.section_links} or {session.routine_entry.section_id}
    return {session.timetable_entry.section_id}
