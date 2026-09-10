from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
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
        .where(
            Section.batch_id == period.batch_id,
            or_(Section.intake_id == period.intake_id, Section.intake_id.is_(None)),
            or_(
                Section.semester_number == period.semester_number,
                Section.semester_number.is_(None),
            ),
        )
        .order_by(Section.name, Section.id)
    ).all()


def target_sections(db: Session, period: CohortSemester) -> list[Section]:
    return db.scalars(
        select(Section)
        .where(
            Section.batch_id == period.batch_id,
            Section.intake_id == period.intake_id,
            Section.semester_number == period.semester_number,
        )
        .order_by(Section.name, Section.id)
    ).all()


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

    target_by_name = {}
    for section in target_list:
        target_by_name.setdefault(section.name.casefold(), section)
    for section in source_list:
        if section.id in mapping:
            continue
        match = target_by_name.get(section.name.casefold())
        if match:
            mapping[section.id] = match.id
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
    if section_ids:
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
    intake_id: int,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
) -> tuple[CohortSemester, CohortSemester, dict[int, int], list[str]]:
    source = db.get(CohortSemester, from_cohort_semester_id)
    target = db.get(CohortSemester, to_cohort_semester_id)
    if source is None or target is None:
        raise PromotionValidationError('Both cohort semesters are required')
    if source.intake_id != intake_id or source.batch_id != batch_id:
        raise PromotionValidationError('Source semester does not match intake and batch')
    if target.intake_id != intake_id or target.batch_id != batch_id:
        raise PromotionValidationError('Target semester does not match intake and batch')
    if target.semester_number != source.semester_number + 1:
        raise PromotionValidationError('Promotions must advance exactly one semester')
    if effective_date != target.start_date:
        raise PromotionValidationError('Effective date must equal the target start date')
    if effective_date <= source.end_date:
        raise PromotionValidationError('Target start date must be after the source end date')
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
    intake_id: int,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
) -> tuple[CohortSemester, CohortSemester, list[PromotionStudent], list[str]]:
    source, target, mapping, errors = validate_promotion_context(
        db,
        intake_id,
        batch_id,
        from_cohort_semester_id,
        to_cohort_semester_id,
        effective_date,
        section_mapping,
        hold_student_ids,
    )
    result: list[PromotionStudent] = []
    day_before = effective_date - timedelta(days=1)
    for student in _source_students(db, source, effective_date):
        enrollment = student_enrollment_at(db, student.id, day_before)
        source_section_id = enrollment.section_id if enrollment else student.section_id
        held = student.id in hold_student_ids
        result.append(
            PromotionStudent(
                student=student,
                source_enrollment=enrollment,
                source_section_id=source_section_id,
                target_section_id=None if held else mapping.get(source_section_id),
                action='hold' if held else 'promote',
                reason='Manually held' if held else None,
            )
        )
    return source, target, result, errors


def apply_promotion(
    db: Session,
    *,
    intake_id: int,
    batch_id: int,
    from_cohort_semester_id: int,
    to_cohort_semester_id: int,
    effective_date: date,
    section_mapping: dict[int, int],
    hold_student_ids: set[int],
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
    )
    if errors:
        raise PromotionValidationError('; '.join(errors))
    run = PromotionRun(
        intake_id=intake_id,
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
    if (
        target_section.batch_id != target.batch_id
        or target_section.intake_id != target.intake_id
        or target_section.semester_number != target.semester_number
    ):
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
                CohortSemester.intake_id == target.intake_id,
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
                intake_id=target.intake_id,
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
