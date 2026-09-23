from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import random

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    AcademicCalendar,
    Batch,
    BatchLevel,
    CohortSemester,
    PromotionRun,
    PromotionRunItem,
    Section,
    Student,
    StudentEnrollment,
)


class PromotionValidationError(ValueError):
    '''A promotion request cannot be safely applied.'''


@dataclass(frozen=True)
class PromotionStudent:
    student: Student
    source_enrollment: StudentEnrollment | None
    source_section_id: int
    target_section_id: int | None
    action: str
    reason: str | None = None


def period_for_context(
    db: Session,
    intake_id: int,
    batch_id: int,
    semester_number: int,
    on_date: date | None = None,
) -> CohortSemester | None:
    query = select(CohortSemester).where(
        CohortSemester.intake_id == intake_id,
        CohortSemester.batch_id == batch_id,
        CohortSemester.semester_number == semester_number,
    )
    if on_date is not None:
        query = query.where(
            CohortSemester.start_date <= on_date,
            CohortSemester.end_date >= on_date,
        )
    return db.scalar(query.order_by(CohortSemester.attempt_number.desc()))


def student_enrollment_at(
    db: Session,
    student_id: int,
    on_date: date,
) -> StudentEnrollment | None:
    return db.scalar(
        select(StudentEnrollment)
        .where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.starts_on <= on_date,
            or_(
                StudentEnrollment.ends_on.is_(None),
                StudentEnrollment.ends_on > on_date,
            ),
            StudentEnrollment.status != 'withdrawn',
        )
        .order_by(StudentEnrollment.starts_on.desc(), StudentEnrollment.id.desc())
        .limit(1)
    )


def student_section_at(db: Session, student_id: int, on_date: date) -> int | None:
    enrollment = student_enrollment_at(db, student_id, on_date)
    if enrollment is not None:
        return enrollment.section_id
    student = db.get(Student, student_id)
    return student.section_id if student else None


def routine_is_active_on_date(db: Session, entry, on_date: date) -> bool:
    '''Legacy routines remain active; period-linked routines are date bounded.'''
    period = getattr(entry, 'cohort_semester', None)
    if period is None and getattr(entry, 'cohort_semester_id', None) is not None:
        period = db.get(CohortSemester, entry.cohort_semester_id)
    if period is None:
        return True
    return period.start_date <= on_date <= period.end_date


def students_for_sections_as_of(
    db: Session,
    section_ids: set[int] | list[int],
    on_date: date,
) -> list[Student]:
    ids = set(section_ids)
    if not ids:
        return []
    candidate_ids = set(
        db.scalars(select(Student.id).where(Student.section_id.in_(ids))).all()
    )
    candidate_ids.update(
        db.scalars(
            select(StudentEnrollment.student_id).where(
                StudentEnrollment.section_id.in_(ids),
                StudentEnrollment.starts_on <= on_date,
                or_(
                    StudentEnrollment.ends_on.is_(None),
                    StudentEnrollment.ends_on > on_date,
                ),
            )
        ).all()
    )
    students = db.scalars(
        select(Student).where(Student.id.in_(candidate_ids)).order_by(Student.roll_number)
    ).all()
    return [
        student
        for student in students
        if student_section_at(db, student.id, on_date) in ids
    ]


def ensure_student_enrollment(
    db: Session,
    student: Student,
    starts_on: date | None = None,
    cohort_semester_id: int | None = None,
) -> StudentEnrollment:
    section = db.get(Section, student.section_id)
    if section is None:
        raise PromotionValidationError('Student section not found')
    starts_on = starts_on or date.today()
    existing = student_enrollment_at(db, student.id, starts_on)
    if existing is not None and existing.section_id == section.id:
        if cohort_semester_id is not None and existing.cohort_semester_id is None:
            existing.cohort_semester_id = cohort_semester_id
        return existing
    period = (
        db.get(CohortSemester, cohort_semester_id)
        if cohort_semester_id is not None
        else db.get(CohortSemester, section.cohort_semester_id)
        if section.cohort_semester_id is not None
        else period_for_context(
            db,
            section.intake_id,
            section.batch_id,
            section.semester_number,
            starts_on,
        )
        if section.intake_id is not None and section.semester_number is not None
        else None
    )
    enrollment = StudentEnrollment(
        student_id=student.id,
        section_id=section.id,
        cohort_semester_id=period.id if period else None,
        starts_on=starts_on,
        status='active',
    )
    db.add(enrollment)
    return enrollment


def source_sections(db: Session, period: CohortSemester) -> list[Section]:
    return db.scalars(
        select(Section)
        .where(Section.batch_id == period.batch_id)
        .order_by(Section.name, Section.id)
    ).all()


def target_sections(db: Session, period: CohortSemester) -> list[Section]:
    return source_sections(db, period)


def resolve_section_mapping(
    db: Session,
    source: CohortSemester,
    target: CohortSemester,
    requested: dict[int, int],
) -> tuple[dict[int, int], list[str]]:
    source_list = source_sections(db, source)
    target_list = target_sections(db, target)
    source_by_id = {section.id: section for section in source_list}
    target_by_id = {section.id: section for section in target_list}
    errors: list[str] = []
    mapping: dict[int, int] = {}

    for source_id, target_id in requested.items():
        source_id = int(source_id)
        target_id = int(target_id)
        if source_id not in source_by_id:
            errors.append(f'Source section {source_id} is not in the source semester')
        elif target_id not in target_by_id:
            errors.append(f'Target section {target_id} is not in the target semester')
        else:
            mapping[source_id] = target_id

    for section in source_list:
        if section.id in mapping:
            continue
        if section.id in target_by_id:
            mapping[section.id] = section.id
    return mapping, errors


def _source_students(
    db: Session,
    source: CohortSemester,
    effective_date: date,
) -> list[Student]:
    day_before = effective_date - timedelta(days=1)
    section_ids = {section.id for section in source_sections(db, source)}
    candidate_ids = set(
        db.scalars(
            select(StudentEnrollment.student_id).where(
                StudentEnrollment.cohort_semester_id == source.id,
                StudentEnrollment.starts_on <= day_before,
                or_(
                    StudentEnrollment.ends_on.is_(None),
                    StudentEnrollment.ends_on > day_before,
                ),
            )
        ).all()
    )
    # Dated semester placements are authoritative once they exist. The legacy
    # Student.section_id cache is only a fallback for cohorts that have not yet
    # received any StudentEnrollment rows.
    if not candidate_ids and section_ids:
        candidate_ids.update(
            student.id
            for student in students_for_sections_as_of(db, section_ids, day_before)
        )
    if not candidate_ids:
        return []
    return db.scalars(
        select(Student).where(Student.id.in_(candidate_ids)).order_by(Student.roll_number)
    ).all()


def validate_promotion_context(
    db: Session,
    intake_id: int | None,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
    require_section_mapping: bool = True,
) -> tuple[CohortSemester, CohortSemester, dict[int, int], list[str]]:
    source = db.get(CohortSemester, from_cohort_semester_id)
    target = db.get(CohortSemester, to_cohort_semester_id)
    if source is None or target is None:
        raise PromotionValidationError('Both cohort semesters are required')
    if source.batch_id != batch_id or target.batch_id != batch_id:
        raise PromotionValidationError('Both semesters must belong to the selected stable batch')
    if intake_id is not None and source.intake_id != intake_id:
        raise PromotionValidationError('The provided intake does not match the source semester')
    if target.semester_number != source.semester_number + 1:
        raise PromotionValidationError('Promotions must advance exactly one semester')
    source_level = db.get(BatchLevel, source.batch_level_id)
    target_level = db.get(BatchLevel, target.batch_level_id)
    if source_level is None or target_level is None:
        raise PromotionValidationError('Both semesters must belong to configured batch levels')
    expected_source_level = ((source.semester_number - 1) // 2) + 1
    expected_target_level = ((target.semester_number - 1) // 2) + 1
    if source_level.level_number != expected_source_level or target_level.level_number != expected_target_level:
        raise PromotionValidationError('Semester numbers do not match their configured levels')
    if source.semester_number in {1, 3, 5}:
        if target_level.id != source_level.id or target.intake_id != source.intake_id:
            raise PromotionValidationError('Within-level progression must keep the same Level and Intake Code')
    elif source.semester_number in {2, 4}:
        if target_level.level_number != source_level.level_number + 1:
            raise PromotionValidationError('Level progression must advance exactly one Level')
        if target.intake_id == source.intake_id:
            raise PromotionValidationError('Level progression requires a new Intake Code')
    else:
        raise PromotionValidationError('Semester 6 is the final semester and cannot be progressed')
    if effective_date != target.start_date:
        raise PromotionValidationError('Effective date must equal the target start date')
    if effective_date <= source.end_date:
        raise PromotionValidationError('Target start date must be after the source end date')
    batch = db.get(Batch, batch_id)
    if batch is None or not (
        batch.start_date <= source.start_date <= source.end_date <= batch.end_date
        and batch.start_date <= target.start_date <= target.end_date <= batch.end_date
    ):
        raise PromotionValidationError('Semester dates must fall within the three-year Batch dates')
    if db.scalar(
        select(AcademicCalendar.id).where(AcademicCalendar.cohort_semester_id == target.id)
    ) is None:
        raise PromotionValidationError(
            'Target Semester is not ready: upload its Academic Calendar PDF first'
        )
    if db.scalar(
        select(PromotionRun.id).where(
            PromotionRun.from_cohort_semester_id == source.id,
            PromotionRun.to_cohort_semester_id == target.id,
            PromotionRun.status == 'applied',
        )
    ):
        raise PromotionValidationError('This cohort-semester transition has already been applied')

    mapping, errors = resolve_section_mapping(db, source, target, section_mapping)
    students = _source_students(db, source, effective_date)
    student_ids = {student.id for student in students}
    unknown_holds = hold_student_ids - student_ids
    if unknown_holds:
        errors.append(
            'Hold list contains students outside the source cohort: '
            + ', '.join(str(student_id) for student_id in sorted(unknown_holds))
        )
    if require_section_mapping:
        missing_sections = sorted(
            {
                student_section_at(db, student.id, effective_date - timedelta(days=1))
                for student in students
            }
            - mapping.keys()
            - {None}
        )
        if missing_sections:
            errors.append(
                'No target section mapping exists for source sections: '
                + ', '.join(str(section_id) for section_id in missing_sections)
            )
    return source, target, mapping, errors


def preview_promotion(
    db: Session,
    intake_id: int | None,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
    placement_strategy: str = 'whole_section',
    target_section_ids: set[int] | None = None,
    manual_overrides: dict[int, int] | None = None,
    random_seed: int = 0,
) -> tuple[CohortSemester, CohortSemester, list[PromotionStudent], list[str]]:
    if placement_strategy not in {'keep_existing', 'whole_section', 'random_balanced'}:
        raise PromotionValidationError('Unknown Section placement strategy')
    manual_overrides = manual_overrides or {}
    source, target, mapping, errors = validate_promotion_context(
        db,
        intake_id,
        batch_id,
        from_cohort_semester_id,
        to_cohort_semester_id,
        effective_date,
        section_mapping,
        hold_student_ids,
        require_section_mapping=placement_strategy == 'whole_section',
    )
    available_targets = {section.id for section in target_sections(db, target)}
    allowed_targets = set(target_section_ids or available_targets)
    invalid_targets = allowed_targets - available_targets
    if invalid_targets:
        errors.append(
            'Target Sections do not belong to the Batch: '
            + ', '.join(str(section_id) for section_id in sorted(invalid_targets))
        )
    invalid_overrides = set(manual_overrides.values()) - allowed_targets
    if invalid_overrides:
        errors.append(
            'Manual overrides contain unavailable target Sections: '
            + ', '.join(str(section_id) for section_id in sorted(invalid_overrides))
        )
    if placement_strategy == 'whole_section':
        invalid_mappings = set(mapping.values()) - allowed_targets
        if invalid_mappings:
            errors.append(
                'Section mapping contains unavailable target Sections: '
                + ', '.join(str(section_id) for section_id in sorted(invalid_mappings))
            )

    source_students = _source_students(db, source, effective_date)
    source_ids = {student.id for student in source_students}
    unknown_overrides = set(manual_overrides) - source_ids
    if unknown_overrides:
        errors.append(
            'Manual overrides contain students outside the source cohort: '
            + ', '.join(str(student_id) for student_id in sorted(unknown_overrides))
        )

    day_before = effective_date - timedelta(days=1)
    prepared = []
    for student in source_students:
        enrollment = student_enrollment_at(db, student.id, day_before)
        source_section_id = enrollment.section_id if enrollment else student.section_id
        prepared.append((student, enrollment, source_section_id))

    assignments: dict[int, int] = {
        student_id: section_id
        for student_id, section_id in manual_overrides.items()
        if student_id not in hold_student_ids and section_id in allowed_targets
    }
    if placement_strategy == 'random_balanced':
        if not allowed_targets:
            errors.append('Random balanced shuffle requires at least one target Section')
        else:
            counts = {section_id: 0 for section_id in sorted(allowed_targets)}
            for section_id in assignments.values():
                counts[section_id] += 1
            remaining = [
                student.id
                for student, _, _ in prepared
                if student.id not in hold_student_ids and student.id not in assignments
            ]
            random.Random(random_seed).shuffle(remaining)
            for student_id in remaining:
                section_id = min(counts, key=lambda item: (counts[item], item))
                assignments[student_id] = section_id
                counts[section_id] += 1
    else:
        for student, _, source_section_id in prepared:
            if student.id in hold_student_ids or student.id in assignments:
                continue
            target_section_id = (
                source_section_id
                if placement_strategy == 'keep_existing'
                else mapping.get(source_section_id)
            )
            if target_section_id not in allowed_targets:
                errors.append(
                    f'No valid target Section is configured for student {student.id}'
                )
            else:
                assignments[student.id] = target_section_id

    result: list[PromotionStudent] = []
    for student, enrollment, source_section_id in prepared:
        held = student.id in hold_student_ids
        result.append(
            PromotionStudent(
                student=student,
                source_enrollment=enrollment,
                source_section_id=source_section_id,
                target_section_id=None if held else assignments.get(student.id),
                action='hold' if held else 'promote',
                reason=(
                    'Manually held'
                    if held
                    else 'Manual Section override'
                    if student.id in manual_overrides
                    else None
                ),
            )
        )
    return source, target, result, errors


def placement_signature(
    source: CohortSemester,
    target: CohortSemester,
    students: list[PromotionStudent],
) -> str:
    payload = {
        'source': source.id,
        'target': target.id,
        'students': [
            {
                'student_id': item.student.id,
                'source_section_id': item.source_section_id,
                'target_section_id': item.target_section_id,
                'action': item.action,
            }
            for item in students
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def preview_initial_assignment(
    db: Session,
    *,
    cohort_semester_id: int,
    student_ids: set[int] | None,
    placement_strategy: str,
    target_section_ids: set[int],
    section_mapping: dict[int, int],
    manual_overrides: dict[int, int],
    hold_student_ids: set[int],
    random_seed: int = 0,
) -> tuple[CohortSemester, list[PromotionStudent], list[str]]:
    target = db.get(CohortSemester, cohort_semester_id)
    if target is None:
        raise PromotionValidationError('Target Semester not found')
    if db.scalar(
        select(AcademicCalendar.id).where(AcademicCalendar.cohort_semester_id == target.id)
    ) is None:
        raise PromotionValidationError(
            'Target Semester is not ready: upload its Academic Calendar PDF first'
        )
    if placement_strategy not in {'keep_existing', 'whole_section', 'random_balanced'}:
        raise PromotionValidationError('Unknown Section placement strategy')
    available = {section.id for section in target_sections(db, target)}
    allowed = set(target_section_ids or available)
    errors: list[str] = []
    if allowed - available:
        errors.append('Every target Section must belong to the target Batch')
    if set(manual_overrides.values()) - allowed:
        errors.append('Manual overrides contain an unavailable target Section')

    explicitly_selected = bool(student_ids)
    if explicitly_selected:
        students = db.scalars(
            select(Student).where(Student.id.in_(student_ids)).order_by(Student.roll_number)
        ).all()
        missing = student_ids - {student.id for student in students}
        if missing:
            errors.append('Students not found: ' + ', '.join(str(item) for item in sorted(missing)))
    else:
        students = db.scalars(
            select(Student)
            .join(Section, Student.section_id == Section.id)
            .where(
                Section.batch_id == target.batch_id,
                ~Student.enrollments.any(
                    StudentEnrollment.cohort_semester_id == target.id
                ),
            )
            .order_by(Student.roll_number)
        ).all()
    outside = [student.id for student in students if student.section.batch_id != target.batch_id]
    if outside:
        errors.append(
            'Students outside the target Batch: '
            + ', '.join(str(item) for item in sorted(outside))
        )
    existing = set(db.scalars(
        select(StudentEnrollment.student_id).where(
            StudentEnrollment.cohort_semester_id == target.id,
            StudentEnrollment.student_id.in_([student.id for student in students]),
        )
    ).all()) if students else set()
    if existing and explicitly_selected:
        errors.append(
            'Students already placed in this Semester: '
            + ', '.join(str(item) for item in sorted(existing))
        )
    unknown_holds = hold_student_ids - {student.id for student in students}
    unknown_overrides = set(manual_overrides) - {student.id for student in students}
    if unknown_holds:
        errors.append('Hold list includes students outside this assignment')
    if unknown_overrides:
        errors.append('Manual overrides include students outside this assignment')

    assignments = {
        student_id: section_id
        for student_id, section_id in manual_overrides.items()
        if student_id not in hold_student_ids and section_id in allowed
    }
    if placement_strategy == 'random_balanced':
        if not allowed:
            errors.append('Random balanced shuffle requires at least one target Section')
        else:
            counts = {section_id: 0 for section_id in sorted(allowed)}
            for section_id in assignments.values():
                counts[section_id] += 1
            remaining = [
                student.id for student in students
                if student.id not in assignments and student.id not in hold_student_ids
            ]
            random.Random(random_seed).shuffle(remaining)
            for student_id in remaining:
                section_id = min(counts, key=lambda item: (counts[item], item))
                assignments[student_id] = section_id
                counts[section_id] += 1
    else:
        for student in students:
            if student.id in assignments or student.id in hold_student_ids:
                continue
            section_id = (
                student.section_id
                if placement_strategy == 'keep_existing'
                else section_mapping.get(student.section_id)
            )
            if section_id not in allowed:
                errors.append(f'No valid target Section is configured for student {student.id}')
            else:
                assignments[student.id] = section_id

    decisions = []
    for student in students:
        prior = student_enrollment_at(db, student.id, target.start_date - timedelta(days=1))
        decisions.append(
            PromotionStudent(
                student=student,
                source_enrollment=prior,
                source_section_id=prior.section_id if prior else student.section_id,
                target_section_id=(
                    None if student.id in hold_student_ids else assignments.get(student.id)
                ),
                action='hold' if student.id in hold_student_ids else 'assign',
                reason=(
                    'Manually held'
                    if student.id in hold_student_ids
                    else 'Manual Section override'
                    if student.id in manual_overrides
                    else None
                ),
            )
        )
    return target, decisions, errors


def apply_initial_assignment(
    db: Session,
    *,
    preview_signature: str,
    **kwargs,
) -> tuple[CohortSemester, list[PromotionStudent]]:
    target, decisions, errors = preview_initial_assignment(db, **kwargs)
    if errors:
        raise PromotionValidationError('; '.join(errors))
    if preview_signature != placement_signature(target, target, decisions):
        raise PromotionValidationError('The roster changed after preview; preview again before applying')
    for item in decisions:
        if item.action == 'hold':
            continue
        prior = item.source_enrollment
        if prior is not None and prior.cohort_semester_id != target.id:
            if prior.starts_on >= target.start_date:
                raise PromotionValidationError(
                    f'Student {item.student.id} has an overlapping placement'
                )
            prior.ends_on = target.start_date
            prior.status = 'completed'
        enrollment = StudentEnrollment(
            student_id=item.student.id,
            section_id=item.target_section_id,
            cohort_semester_id=target.id,
            starts_on=target.start_date,
            status='active',
        )
        db.add(enrollment)
        item.student.section_id = item.target_section_id
    db.flush()
    return target, decisions


def move_student_section(
    db: Session,
    *,
    student_id: int,
    cohort_semester_id: int,
    target_section_id: int,
    effective_date: date,
) -> StudentEnrollment:
    student = db.get(Student, student_id)
    semester = db.get(CohortSemester, cohort_semester_id)
    section = db.get(Section, target_section_id)
    if student is None or semester is None or section is None:
        raise PromotionValidationError('Student, Semester, or target Section not found')
    if section.batch_id != semester.batch_id:
        raise PromotionValidationError('Target Section does not belong to the Semester Batch')
    if not semester.start_date <= effective_date <= semester.end_date:
        raise PromotionValidationError('Move date must fall within the Semester dates')
    current = db.scalar(
        select(StudentEnrollment)
        .where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.cohort_semester_id == cohort_semester_id,
            StudentEnrollment.starts_on <= effective_date,
            or_(StudentEnrollment.ends_on.is_(None), StudentEnrollment.ends_on > effective_date),
            StudentEnrollment.status != 'withdrawn',
        )
        .order_by(StudentEnrollment.starts_on.desc(), StudentEnrollment.id.desc())
        .limit(1)
    )
    if current is None:
        raise PromotionValidationError('Student has no active placement in that Semester')
    if current.section_id == target_section_id:
        raise PromotionValidationError('Student is already in the selected Section')
    if effective_date <= current.starts_on:
        raise PromotionValidationError('Move date must be after the current placement start date')
    current.ends_on = effective_date
    current.status = 'moved'
    moved = StudentEnrollment(
        student_id=student_id,
        section_id=target_section_id,
        cohort_semester_id=cohort_semester_id,
        starts_on=effective_date,
        status='active',
    )
    db.add(moved)
    db.flush()
    student.section_id = target_section_id
    return moved


def apply_promotion(
    db: Session,
    *,
    intake_id: int | None,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
    placement_strategy: str = 'whole_section',
    target_section_ids: set[int] | None = None,
    manual_overrides: dict[int, int] | None = None,
    random_seed: int = 0,
    preview_signature: str | None = None,
    created_by: int | None = None,
    notes: str | None = None,
) -> tuple[PromotionRun, list[PromotionStudent]]:
    source, target, students, errors = preview_promotion(
        db,
        intake_id,
        batch_id,
        from_cohort_semester_id,
        to_cohort_semester_id,
        effective_date,
        section_mapping,
        hold_student_ids,
        placement_strategy,
        target_section_ids,
        manual_overrides,
        random_seed,
    )
    if errors:
        raise PromotionValidationError('; '.join(errors))
    if preview_signature is not None and preview_signature != placement_signature(source, target, students):
        raise PromotionValidationError('The roster changed after preview; preview again before applying')
    run = PromotionRun(
        intake_id=source.intake_id,
        batch_id=batch_id,
        from_cohort_semester_id=source.id,
        to_cohort_semester_id=target.id,
        effective_date=effective_date,
        created_by=created_by,
        notes=notes,
        status='applied',
    )
    db.add(run)
    db.flush()
    for item in students:
        enrollment = item.source_enrollment
        if enrollment is None:
            enrollment = StudentEnrollment(
                student_id=item.student.id,
                section_id=item.source_section_id,
                cohort_semester_id=source.id,
                starts_on=source.start_date,
                status='active',
            )
            db.add(enrollment)
            db.flush()
        if enrollment.cohort_semester_id is None:
            enrollment.cohort_semester_id = source.id
        if item.action == 'hold':
            enrollment.status = 'held'
        else:
            enrollment.ends_on = effective_date
            enrollment.status = 'completed'
        enrollment.promotion_run_id = run.id
        target_enrollment = None
        if item.action == 'promote':
            target_enrollment = StudentEnrollment(
                student_id=item.student.id,
                section_id=item.target_section_id,
                cohort_semester_id=target.id,
                starts_on=effective_date,
                status='active',
                promotion_run_id=run.id,
            )
            db.add(target_enrollment)
            item.student.section_id = item.target_section_id
        db.add(
            PromotionRunItem(
                promotion_run_id=run.id,
                student_id=item.student.id,
                source_enrollment_id=enrollment.id,
                target_enrollment_id=target_enrollment.id if target_enrollment else None,
                source_section_id=item.source_section_id,
                target_section_id=item.target_section_id,
                action=item.action,
                reason=item.reason,
            )
        )
    db.flush()
    return run, students


def release_held_student(
    db: Session,
    run: PromotionRun,
    student_id: int,
    target_section_id: int,
    reason: str | None = None,
) -> StudentEnrollment:
    item = db.scalar(
        select(PromotionRunItem).where(
            PromotionRunItem.promotion_run_id == run.id,
            PromotionRunItem.student_id == student_id,
        )
    )
    if item is None or item.action != 'hold':
        raise PromotionValidationError('That student is not held in this promotion run')
    target = db.get(CohortSemester, run.to_cohort_semester_id)
    target_section = db.get(Section, target_section_id)
    if target is None or target_section is None:
        raise PromotionValidationError('Target semester or section not found')
    if target_section.batch_id != target.batch_id:
        raise PromotionValidationError('Target section does not belong to the promotion target semester')
    source = db.get(StudentEnrollment, item.source_enrollment_id)
    student = db.get(Student, student_id)
    if source is None or student is None:
        raise PromotionValidationError('Held student history is incomplete')
    source.ends_on = run.effective_date
    source.status = 'completed'
    target_enrollment = StudentEnrollment(
        student_id=student_id,
        section_id=target_section_id,
        cohort_semester_id=target.id,
        starts_on=run.effective_date,
        status='active',
        promotion_run_id=run.id,
    )
    db.add(target_enrollment)
    db.flush()
    student.section_id = target_section_id
    item.action = 'promote'
    item.target_section_id = target_section_id
    item.target_enrollment_id = target_enrollment.id
    item.reason = reason or 'Released from hold'
    db.flush()
    return target_enrollment


def process_due_promotions(db: Session, on_date: date | None = None) -> int:
    '''Apply ready transitions whose target semester starts on or before on_date.'''
    on_date = on_date or date.today()
    targets = db.scalars(
        select(CohortSemester)
        .where(
            CohortSemester.start_date <= on_date,
            CohortSemester.status.in_(['planned', 'active']),
        )
        .order_by(CohortSemester.start_date, CohortSemester.id)
    ).all()
    applied = 0
    for target in targets:
        source = db.scalar(
            select(CohortSemester)
            .where(
                CohortSemester.batch_id == target.batch_id,
                CohortSemester.semester_number == target.semester_number - 1,
                CohortSemester.end_date < target.start_date,
            )
            .order_by(CohortSemester.end_date.desc(), CohortSemester.id.desc())
            .limit(1)
        )
        if source is None or db.scalar(
            select(PromotionRun.id).where(
                PromotionRun.from_cohort_semester_id == source.id,
                PromotionRun.to_cohort_semester_id == target.id,
                PromotionRun.status == 'applied',
            )
        ):
            continue
        try:
            apply_promotion(
                db,
                intake_id=source.intake_id,
                batch_id=target.batch_id,
                from_cohort_semester_id=source.id,
                to_cohort_semester_id=target.id,
                effective_date=target.start_date,
                section_mapping={},
                hold_student_ids=set(),
            )
            db.commit()
            applied += 1
        except PromotionValidationError:
            db.rollback()
    return applied
