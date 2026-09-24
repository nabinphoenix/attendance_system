"""Create the approved live presentation academic dataset.

This command is deliberately separate from the reset command.  It refuses to
run unless the reset tables are empty, creates exactly the two requested Batch /
Level 3 / Intake contexts, and never derives semester dates from a batch date.

Run from ``backend`` only after a verified reset::

    python seed_presentation_data.py --confirm-live-seed --admin-id 2
"""

from __future__ import annotations

import argparse
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.academic.models import (
    AcademicModule,
    Batch,
    BatchLevel,
    ClassType,
    CohortSemester,
    Intake,
    ModuleOffering,
    Program,
    Room,
    RoutineEntry,
    RoutineEntrySection,
    Section,
    Student,
    StudentEnrollment,
    Teacher,
    TimeSlot,
)
from app.modules.analytics.service import evaluate_saved_session
from app.modules.attendance.models import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, SessionStatus


EXPECTED_PROGRAM_NAME = "BSc.IT"
SEPTEMBER_COURSES = (
    "CT012-3-3-CSM",
    "CT024-3-3-DCOMS",
    "CT050-3-3-PRMGT",
    "CT052-3-3-IIT",
    "CT081-3-3-MWM",
    "CT097-3-3-CSVC",
)
JANUARY_COURSES = (
    "CT106-3-2-SNA",
    "CT038-3-2-OODJ",
    "CT050-3-3-PRMGT",
    "CT052-3-3-IIT",
    "CT081-3-3-MWM",
    "CT097-3-3-CSVC",
)


class SeedError(RuntimeError):
    """Raised whenever the production presentation seed is unsafe to run."""


@dataclass(frozen=True)
class StudentSeed:
    section: str
    name: str
    email: str


@dataclass(frozen=True)
class BatchSeed:
    name: str
    batch_start: date
    batch_end: date
    intake_code: str
    intake_start: date
    semester_five_start: date
    semester_five_end: date
    semester_six_start: date
    semester_six_end: date
    section_names: tuple[str, str]
    course_codes: tuple[str, ...]
    students: tuple[StudentSeed, ...]


# These explicit presentation dates were approved for this live demo seed. They
# are never calculated from either Batch date. Academic calendars are omitted
# from this presentation seed at the administrator's request.
PRESENTATION_BATCHES = (
    BatchSeed(
        name="September 2023",
        batch_start=date(2023, 9, 18),
        batch_end=date(2026, 9, 17),
        intake_code="NPT3F2509IT",
        intake_start=date(2025, 9, 1),
        semester_five_start=date(2026, 9, 1),
        semester_five_end=date(2026, 12, 31),
        semester_six_start=date(2027, 1, 1),
        semester_six_end=date(2027, 6, 30),
        section_names=("A1", "A2"),
        course_codes=SEPTEMBER_COURSES,
        students=(
            StudentSeed("A1", "Anisha Karki", "dreamerdeepak7@gmail.com"),
            StudentSeed("A1", "Sushmita Bhandari", "juniorjkberlin@gmail.com"),
            StudentSeed("A1", "Bibek Poudel", "livecricfootnepal@gmail.com"),
            StudentSeed("A1", "Deepak Shrestha", "passionatedeepak7@gmail.com"),
            StudentSeed("A1", "Sneha Joshi", "tekbahadurnepali007@gmail.com"),
            StudentSeed("A1", "Samir Tamang", "xer.xes.7.ai@gmail.com"),
            StudentSeed("A1", "Aarav Sharma", "aarav.sharmasep26@cps.edu.np"),
            StudentSeed("A1", "Sita Rai", "sita.raisep26@cps.edu.np"),
            StudentSeed("A1", "Bikash Thapa", "bikash.thapasep26@cps.edu.np"),
            StudentSeed("A2", "Asmita Rai", "deepakbdblog@gmail.com"),
            StudentSeed("A2", "Prisha Shrestha", "deepak.shrestha23@cps.edu.np"),
            StudentSeed("A2", "Aayush Khadka", "jack13son13@gmail.com"),
            StudentSeed("A2", "Rojan Thapa", "laxmistha633@gmail.com"),
            StudentSeed("A2", "Roshan KC", "sunitanepali7741@gmail.com"),
            StudentSeed("A2", "Nisha Acharya", "techsavvykid13@gmail.com"),
            StudentSeed("A2", "Aayush Dhakal", "aayush.dhakalsep26@cps.edu.np"),
            StudentSeed("A2", "Prerana Rai", "prerana.raisep26@cps.edu.np"),
        ),
    ),
    BatchSeed(
        name="January 2024",
        batch_start=date(2024, 1, 15),
        batch_end=date(2027, 1, 14),
        intake_code="NPT3F2601IT",
        intake_start=date(2026, 1, 1),
        semester_five_start=date(2026, 9, 1),
        semester_five_end=date(2026, 12, 31),
        semester_six_start=date(2027, 1, 1),
        semester_six_end=date(2027, 6, 30),
        section_names=("A3", "A4"),
        course_codes=JANUARY_COURSES,
        students=(
            StudentSeed("A3", "Sanjana Gurung", "boysbhundol@gmail.com"),
            StudentSeed("A3", "Niraj Maharjan", "deepak.shikshyanepal@gmail.com"),
            StudentSeed("A3", "Sujal Adhikari", "livemusicnepal7@gmail.com"),
            StudentSeed("A3", "Ritika Basnet", "nabin7nepali@gmail.com"),
            StudentSeed("A3", "Prabin Lama", "rupa.nepali033@gmail.com"),
            StudentSeed("A4", "Nabin Nepali", "nabin.nepalisep26@cps.edu.np"),
            StudentSeed("A4", "Rojina Thapa", "rojina.thapasep26@cps.edu.np"),
            StudentSeed("A4", "Sagar Bista", "sagar.bistasep26@cps.edu.np"),
            StudentSeed("A4", "Alisha Tamang", "alisha.tamangsep26@cps.edu.np"),
        ),
    ),
)

RESET_REQUIRED_EMPTY_TABLES = (
    Student,
    StudentEnrollment,
    Batch,
    Intake,
    BatchLevel,
    CohortSemester,
    Section,
    ModuleOffering,
    RoutineEntry,
    ClassSession,
    AttendanceRecord,
)
def count_rows(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def get_program(db: Session) -> Program:
    programs = db.scalars(
        select(Program).where(func.lower(Program.name) == EXPECTED_PROGRAM_NAME.casefold())
    ).all()
    if len(programs) != 1:
        raise SeedError(f"Expected exactly one {EXPECTED_PROGRAM_NAME} program, found {len(programs)}")
    return programs[0]


def require_empty_reset_scope(db: Session) -> None:
    non_empty = {
        model.__tablename__: count_rows(db, model)
        for model in RESET_REQUIRED_EMPTY_TABLES
        if count_rows(db, model)
    }
    if non_empty:
        raise SeedError(
            "Refusing to seed over existing academic data; run the verified controlled reset first: "
            f"{non_empty}"
        )


def required_modules(db: Session, college_id: int, codes: Iterable[str]) -> dict[str, AcademicModule]:
    expected = set(codes)
    modules = db.scalars(
        select(AcademicModule).where(
            AcademicModule.college_id == college_id,
            AcademicModule.code.in_(expected),
        )
    ).all()
    by_code = {module.code: module for module in modules}
    missing = sorted(expected.difference(by_code))
    if missing:
        raise SeedError(f"Required Course records are missing: {', '.join(missing)}")
    return by_code


def reusable_records(db: Session, college_id: int) -> tuple[list[Teacher], list[Room], dict[str, ClassType], list[TimeSlot]]:
    teachers = db.scalars(
        select(Teacher).where(Teacher.college_id == college_id).order_by(Teacher.id)
    ).all()
    rooms = db.scalars(
        select(Room).where(Room.college_id == college_id).order_by(Room.id)
    ).all()
    class_types = {
        class_type.name.casefold(): class_type
        for class_type in db.scalars(
            select(ClassType).where(ClassType.college_id == college_id)
        ).all()
    }
    slots = db.scalars(
        select(TimeSlot)
        .where(TimeSlot.college_id == college_id)
        .order_by(TimeSlot.start_time, TimeSlot.end_time, TimeSlot.id)
    ).all()
    required_types = {"lecture", "tutorial", "practical"}
    if not teachers or not rooms or not required_types.issubset(class_types) or not slots:
        raise SeedError("Teachers, rooms, Lecture/Tutorial/Practical types, and Time Slots must exist before seeding")
    return teachers, rooms, class_types, slots


def _overlaps(left: TimeSlot, right: TimeSlot) -> bool:
    return left.start_time < right.end_time and left.end_time > right.start_time


def next_conflict_free_slot(
    scheduled: list[tuple[int, TimeSlot, int, int, frozenset[int]]],
    *,
    section_ids: set[int],
    teachers: list[Teacher],
    rooms: list[Room],
    slots: list[TimeSlot],
) -> tuple[int, TimeSlot, Teacher, Room]:
    """Choose a weekly coordinate free for its teacher, room, and sections."""
    for day_of_week in range(7):
        for slot in slots:
            for teacher in teachers:
                for room in rooms:
                    conflict = any(
                        existing_day == day_of_week
                        and _overlaps(existing_slot, slot)
                        and (
                            existing_teacher_id == teacher.id
                            or existing_room_id == room.id
                            or existing_section_ids.intersection(section_ids)
                        )
                        for existing_day, existing_slot, existing_teacher_id, existing_room_id, existing_section_ids in scheduled
                    )
                    if not conflict:
                        return day_of_week, slot, teacher, room
    raise SeedError("Not enough conflict-free Teacher / Room / Time Slot capacity for the requested routines")


def create_student(
    db: Session,
    *,
    seed: StudentSeed,
    section: Section,
    cohort_semester: CohortSemester,
    college_id: int,
    roll_number: str,
) -> Student:
    user = User(
        name=seed.name,
        email=seed.email.casefold(),
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=UserRole.STUDENT,
        college_id=college_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    student = Student(
        user_id=user.id,
        section_id=section.id,
        roll_number=roll_number,
        name=seed.name,
        email=user.email,
        college_id=college_id,
    )
    db.add(student)
    db.flush()
    db.add(
        StudentEnrollment(
            student_id=student.id,
            section_id=section.id,
            cohort_semester_id=cohort_semester.id,
            starts_on=cohort_semester.start_date,
            ends_on=None,
            status="active",
            college_id=college_id,
        )
    )
    return student


def create_attendance_demo(
    db: Session,
    *,
    routine: RoutineEntry,
    students: list[Student],
    present_counts: list[int],
    semester: CohortSemester,
    college_id: int,
) -> int:
    if len(students) != len(present_counts):
        raise SeedError("Attendance demo students and percentages are inconsistent")
    if any(count < 0 or count > 10 for count in present_counts):
        raise SeedError("Attendance presentation data must use ten sessions per student")
    routine_end = min(date.today(), semester.end_date)
    routine_date = routine_end - timedelta(days=9)
    if routine_date < semester.start_date:
        raise SeedError("The approved Semester 5 dates cannot contain ten attendance sessions")
    for offset in range(10):
        session_date = routine_date + timedelta(days=offset)
        started_at = datetime.combine(session_date, time(9, 0), tzinfo=UTC)
        class_session = ClassSession(
            routine_entry_id=routine.id,
            session_date=session_date,
            effective_teacher_id=routine.teacher_id,
            effective_room=routine.room.name,
            status=SessionStatus.COMPLETED,
            started_at=started_at,
            finalized_at=started_at + timedelta(hours=1),
            college_id=college_id,
        )
        db.add(class_session)
        db.flush()
        for student, present_count in zip(students, present_counts, strict=True):
            present = offset < present_count
            db.add(
                AttendanceRecord(
                    class_session_id=class_session.id,
                    student_id=student.id,
                    status=AttendanceStatus.PRESENT if present else AttendanceStatus.ABSENT,
                    method=AttendanceMethod.MANUAL,
                    check_in_time=started_at + timedelta(minutes=5) if present else None,
                    college_id=college_id,
                )
            )
    return 10


def seed(db: Session, *, admin_id: int, dry_run: bool) -> dict[str, int]:
    admin = db.get(User, admin_id)
    if admin is None or not admin.is_active or admin.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise SeedError(f"Seed administrator ID {admin_id} is not an active Admin/SuperAdmin")
    require_empty_reset_scope(db)
    program = get_program(db)
    college_id = program.college_id
    if college_id is None:
        raise SeedError("BSc.IT must belong to a college")
    all_codes = tuple(dict.fromkeys(SEPTEMBER_COURSES + JANUARY_COURSES))
    modules = required_modules(db, college_id, all_codes)
    teachers, rooms, class_types, slots = reusable_records(db, college_id)

    counts = {
        "batches": 0,
        "levels": 0,
        "semesters": 0,
        "calendars": 0,
        "sections": 0,
        "students": 0,
        "enrollments": 0,
        "course_assignments": 0,
        "routines": 0,
        "class_sessions": 0,
        "attendance_records": 0,
    }
    contexts: dict[str, dict] = {}
    scheduled: list[tuple[int, TimeSlot, int, int, frozenset[int]]] = []

    for batch_spec in PRESENTATION_BATCHES:
        batch = Batch(
            name=batch_spec.name,
            program_id=program.id,
            start_date=batch_spec.batch_start,
            end_date=batch_spec.batch_end,
            college_id=college_id,
        )
        intake = Intake(
            name=None,
            code=batch_spec.intake_code,
            start_date=batch_spec.intake_start,
            program_id=program.id,
            college_id=college_id,
        )
        db.add_all([batch, intake])
        db.flush()
        level = BatchLevel(
            batch_id=batch.id,
            level_number=3,
            intake_id=intake.id,
            college_id=college_id,
        )
        db.add(level)
        db.flush()
        semester_five = CohortSemester(
            batch_id=batch.id,
            intake_id=intake.id,
            batch_level_id=level.id,
            semester_number=5,
            display_name="Semester 5",
            start_date=batch_spec.semester_five_start,
            end_date=batch_spec.semester_five_end,
            status="current",
            college_id=college_id,
        )
        semester_six = CohortSemester(
            batch_id=batch.id,
            intake_id=intake.id,
            batch_level_id=level.id,
            semester_number=6,
            display_name="Semester 6",
            start_date=batch_spec.semester_six_start,
            end_date=batch_spec.semester_six_end,
            status="planned",
            college_id=college_id,
        )
        db.add_all([semester_five, semester_six])
        db.flush()
        sections: dict[str, Section] = {}
        for section_name in batch_spec.section_names:
            section = Section(
                name=section_name,
                batch_id=batch.id,
                intake_id=None,
                semester_number=None,
                cohort_semester_id=None,
                college_id=college_id,
            )
            db.add(section)
            db.flush()
            sections[section_name] = section
        students: dict[str, list[Student]] = {name: [] for name in batch_spec.section_names}
        counters = {name: 0 for name in batch_spec.section_names}
        for student_seed in batch_spec.students:
            counters[student_seed.section] += 1
            student = create_student(
                db,
                seed=student_seed,
                section=sections[student_seed.section],
                cohort_semester=semester_five,
                college_id=college_id,
                roll_number=f"{batch_spec.intake_code}-{student_seed.section}-{counters[student_seed.section]:02d}",
            )
            students[student_seed.section].append(student)
        offerings: dict[str, ModuleOffering] = {}
        for course_code in batch_spec.course_codes:
            offering = ModuleOffering(
                academic_module_id=modules[course_code].id,
                intake_id=intake.id,
                batch_id=batch.id,
                semester_number=5,
                cohort_semester_id=semester_five.id,
                inherit_all_sections=False,
                is_active=True,
                college_id=college_id,
            )
            offering.sections = [sections[name] for name in batch_spec.section_names]
            db.add(offering)
            db.flush()
            offerings[course_code] = offering
            routine_groups = (
                ("lecture", list(batch_spec.section_names)),
                ("tutorial", [batch_spec.section_names[0]]),
                ("tutorial", [batch_spec.section_names[1]]),
                ("practical", [batch_spec.section_names[0]]),
                ("practical", [batch_spec.section_names[1]]),
            )
            for class_kind, group_names in routine_groups:
                group_sections = [sections[name] for name in group_names]
                group_ids = {section.id for section in group_sections}
                day_of_week, slot, teacher, room = next_conflict_free_slot(
                    scheduled,
                    section_ids=group_ids,
                    teachers=teachers,
                    rooms=rooms,
                    slots=slots,
                )
                routine = RoutineEntry(
                    intake_id=intake.id,
                    semester_number=5,
                    cohort_semester_id=semester_five.id,
                    section_id=group_sections[0].id,
                    module_id=modules[course_code].id,
                    module_offering_id=offering.id,
                    class_type_id=class_types[class_kind].id,
                    teacher_id=teacher.id,
                    room_id=room.id,
                    day_of_week=day_of_week,
                    time_slot_id=slot.id,
                    college_id=college_id,
                )
                db.add(routine)
                db.flush()
                for section in group_sections:
                    db.add(
                        RoutineEntrySection(
                            routine_entry_id=routine.id,
                            section_id=section.id,
                            college_id=college_id,
                        )
                    )
                scheduled.append((day_of_week, slot, teacher.id, room.id, frozenset(group_ids)))
                if class_kind == "lecture":
                    offerings[f"{course_code}:lecture"] = routine
        contexts[batch_spec.name] = {
            "batch": batch,
            "intake": intake,
            "semester_five": semester_five,
            "semester_six": semester_six,
            "sections": sections,
            "students": students,
            "offerings": offerings,
        }
        counts["batches"] += 1
        counts["levels"] += 1
        counts["semesters"] += 2
        counts["sections"] += 2
        counts["students"] += len(batch_spec.students)
        counts["enrollments"] += len(batch_spec.students)
        counts["course_assignments"] += len(batch_spec.course_codes)
        counts["routines"] += len(batch_spec.course_codes) * 5

    # 10 observations each: the two September Cloud students are 70% and 80%;
    # one January OODJ student is 70%.  No other student receives attendance
    # records, so no other student can receive a threshold email from this seed.
    september = contexts["September 2023"]
    january = contexts["January 2024"]
    counts["class_sessions"] += create_attendance_demo(
        db,
        routine=september["offerings"]["CT097-3-3-CSVC:lecture"],
        students=[september["students"]["A1"][0], september["students"]["A1"][1]],
        present_counts=[7, 8],
        semester=september["semester_five"],
        college_id=college_id,
    )
    counts["attendance_records"] += 20
    counts["class_sessions"] += create_attendance_demo(
        db,
        routine=january["offerings"]["CT038-3-2-OODJ:lecture"],
        students=[january["students"]["A3"][0]],
        present_counts=[7],
        semester=january["semester_five"],
        college_id=college_id,
    )
    counts["attendance_records"] += 10

    if dry_run:
        db.rollback()
        return counts

    db.commit()

    # Queue only the two below-threshold emails using the normal application
    # service.  The 80% record is evaluated too but cannot create an alert.
    for routine in (
        september["offerings"]["CT097-3-3-CSVC:lecture"],
        january["offerings"]["CT038-3-2-OODJ:lecture"],
    ):
        session_id = db.scalar(
            select(ClassSession.id)
            .where(ClassSession.routine_entry_id == routine.id)
            .order_by(ClassSession.session_date.desc(), ClassSession.id.desc())
            .limit(1)
        )
        if session_id is None:
            raise SeedError("Attendance demonstration session was not created")
        evaluate_saved_session(db, int(session_id), actor_id=admin.id, send_alerts=True)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-seed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--admin-id", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run and args.confirm_live_seed:
        raise SystemExit("Use either --dry-run or --confirm-live-seed, not both")
    if not args.dry_run and not args.confirm_live_seed:
        raise SystemExit("Refusing to seed live data. Pass --confirm-live-seed explicitly.")
    with SessionLocal() as db:
        try:
            counts = seed(db, admin_id=args.admin_id, dry_run=args.dry_run)
        except Exception:
            db.rollback()
            raise
    label = "Dry-run presentation data" if args.dry_run else "Presentation data created"
    print(label + ":")
    for key, value in counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
