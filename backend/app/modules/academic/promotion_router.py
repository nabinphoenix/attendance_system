from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, func, select

from app.core.dependencies import DbSession, require_role
from app.modules.identity.models import User
from app.modules.operations.service import log_audit

from .models import AcademicCalendar, Batch, BatchLevel, CohortSemester, PromotionRun, PromotionRunItem, Student, StudentEnrollment
from .promotion_service import (
    PromotionValidationError,
    apply_initial_assignment,
    apply_promotion,
    move_student_section,
    placement_signature,
    preview_initial_assignment,
    preview_promotion,
    release_held_student,
)


class CohortSemesterCreate(BaseModel):
    batch_level_id: int
    semester_number: int = Field(ge=1, le=6)
    attempt_number: int = Field(default=1, ge=1)
    start_date: date
    end_date: date
    status: str = 'planned'


class CohortSemesterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_level_id: int
    level_number: int
    intake_id: int
    batch_id: int
    semester_number: int
    attempt_number: int
    start_date: date
    end_date: date
    status: str
    calendar_uploaded: bool
    intake_code: str | None = None
    batch_name: str | None = None
    label: str | None = None


class CohortSemesterUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None


class PromotionRequest(BaseModel):
    # Retained for old clients as the source-intake context. A cohort may move
    # to a new intake after Semester 2 or Semester 4.
    intake_id: int | None = None
    batch_id: int
    from_cohort_semester_id: int
    to_cohort_semester_id: int
    effective_date: date
    section_mapping: dict[int, int] = Field(default_factory=dict)
    placement_strategy: Literal['keep_existing', 'whole_section', 'random_balanced'] = 'whole_section'
    target_section_ids: list[int] = Field(default_factory=list)
    manual_overrides: dict[int, int] = Field(default_factory=dict)
    random_seed: int = 0
    hold_student_ids: list[int] = Field(default_factory=list)
    preview_signature: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class PromotionStudentRead(BaseModel):
    id: int
    roll_number: str
    name: str | None
    source_section_id: int
    target_section_id: int | None
    action: str
    reason: str | None


class PromotionPreviewRead(BaseModel):
    source: CohortSemesterRead
    target: CohortSemesterRead
    total_students: int
    promote_count: int
    hold_count: int
    students: list[PromotionStudentRead]
    errors: list[str]
    preview_signature: str


class PromotionRunRead(BaseModel):
    id: int
    intake_id: int
    batch_id: int
    from_cohort_semester_id: int
    to_cohort_semester_id: int
    effective_date: date
    status: str
    notes: str | None
    total_students: int
    promoted_students: int
    held_students: int


class PromotionRunStudentRead(PromotionStudentRead):
    promotion_run_item_id: int


class EnrollmentHistoryRead(BaseModel):
    id: int
    section_id: int
    cohort_semester_id: int | None
    starts_on: date
    ends_on: date | None
    status: str
    promotion_run_id: int | None


class PromotionReleaseRequest(BaseModel):
    target_section_id: int
    reason: str | None = Field(default=None, max_length=255)


class PlacementRequest(BaseModel):
    cohort_semester_id: int
    student_ids: list[int] = Field(default_factory=list)
    placement_strategy: Literal['keep_existing', 'whole_section', 'random_balanced']
    target_section_ids: list[int] = Field(default_factory=list)
    section_mapping: dict[int, int] = Field(default_factory=dict)
    manual_overrides: dict[int, int] = Field(default_factory=dict)
    hold_student_ids: list[int] = Field(default_factory=list)
    random_seed: int = 0
    preview_signature: str | None = None


class PlacementPreviewRead(BaseModel):
    semester: CohortSemesterRead
    total_students: int
    assign_count: int
    hold_count: int
    students: list[PromotionStudentRead]
    errors: list[str]
    preview_signature: str


class SectionMoveRequest(BaseModel):
    cohort_semester_id: int
    target_section_id: int
    effective_date: date
    reason: str | None = Field(default=None, max_length=255)


router = APIRouter(
    prefix='/academic',
    tags=['academic-promotions'],
    dependencies=[Depends(require_role('admin'))],
)


def _semester_read(db, semester: CohortSemester) -> CohortSemesterRead:
    level = semester.batch_level
    return CohortSemesterRead(
        id=semester.id,
        batch_level_id=semester.batch_level_id,
        level_number=level.level_number,
        intake_id=semester.intake_id,
        batch_id=semester.batch_id,
        semester_number=semester.semester_number,
        attempt_number=semester.attempt_number,
        start_date=semester.start_date,
        end_date=semester.end_date,
        status=semester.status,
        calendar_uploaded=db.scalar(
            select(AcademicCalendar.id).where(
                AcademicCalendar.cohort_semester_id == semester.id
            )
        ) is not None,
        intake_code=semester.intake.code if semester.intake else None,
        batch_name=semester.batch.name if semester.batch else None,
        label=f'Semester {semester.semester_number} - {semester.batch.name if semester.batch else semester.batch_id} - {semester.intake.code if semester.intake else semester.intake_id}',
    )


def _preview_response(db, source, target, students, errors) -> PromotionPreviewRead:
    rows = [
        PromotionStudentRead(
            id=item.student.id,
            roll_number=item.student.roll_number,
            name=item.student.name,
            source_section_id=item.source_section_id,
            target_section_id=item.target_section_id,
            action=item.action,
            reason=item.reason,
        )
        for item in students
    ]
    return PromotionPreviewRead(
        source=_semester_read(db, source),
        target=_semester_read(db, target),
        total_students=len(rows),
        promote_count=sum(row.action == 'promote' for row in rows),
        hold_count=sum(row.action == 'hold' for row in rows),
        students=rows,
        errors=errors,
        preview_signature=placement_signature(source, target, students),
    )


def _promotion_kwargs(payload: PromotionRequest) -> dict:
    return {
        'intake_id': payload.intake_id,
        'batch_id': payload.batch_id,
        'from_cohort_semester_id': payload.from_cohort_semester_id,
        'to_cohort_semester_id': payload.to_cohort_semester_id,
        'effective_date': payload.effective_date,
        'section_mapping': payload.section_mapping,
        'hold_student_ids': set(payload.hold_student_ids),
        'placement_strategy': payload.placement_strategy,
        'target_section_ids': set(payload.target_section_ids),
        'manual_overrides': payload.manual_overrides,
        'random_seed': payload.random_seed,
    }


def _placement_kwargs(payload: PlacementRequest) -> dict:
    return {
        'cohort_semester_id': payload.cohort_semester_id,
        'student_ids': set(payload.student_ids) or None,
        'placement_strategy': payload.placement_strategy,
        'target_section_ids': set(payload.target_section_ids),
        'section_mapping': payload.section_mapping,
        'manual_overrides': payload.manual_overrides,
        'hold_student_ids': set(payload.hold_student_ids),
        'random_seed': payload.random_seed,
    }


def _run_read(db, run: PromotionRun) -> PromotionRunRead:
    total, promoted, held = db.execute(
        select(
            func.count(),
            func.sum(func.cast(PromotionRunItem.action == 'promote', Integer)),
            func.sum(func.cast(PromotionRunItem.action == 'hold', Integer)),
        ).where(PromotionRunItem.promotion_run_id == run.id)
    ).one()
    return PromotionRunRead(
        id=run.id,
        intake_id=run.intake_id,
        batch_id=run.batch_id,
        from_cohort_semester_id=run.from_cohort_semester_id,
        to_cohort_semester_id=run.to_cohort_semester_id,
        effective_date=run.effective_date,
        status=run.status,
        notes=run.notes,
        total_students=total or 0,
        promoted_students=promoted or 0,
        held_students=held or 0,
    )


@router.get('/cohort-semesters', response_model=list[CohortSemesterRead])
def cohort_semesters(db: DbSession):
    semesters = db.scalars(
        select(CohortSemester).order_by(
            CohortSemester.start_date,
            CohortSemester.intake_id,
            CohortSemester.batch_id,
            CohortSemester.semester_number,
        )
    ).all()
    return [_semester_read(db, semester) for semester in semesters]


@router.post('/cohort-semesters', response_model=CohortSemesterRead, status_code=201)
def create_cohort_semester(
    payload: CohortSemesterCreate,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    if payload.start_date > payload.end_date:
        raise HTTPException(422, 'Start date must be on or before end date')
    level = db.get(BatchLevel, payload.batch_level_id)
    if level is None:
        raise HTTPException(404, 'Batch Level not found')
    batch = db.get(Batch, level.batch_id)
    allowed = {level.level_number * 2 - 1, level.level_number * 2}
    if payload.semester_number not in allowed:
        raise HTTPException(
            422,
            f'Level {level.level_number} only supports Semesters {min(allowed)} and {max(allowed)}',
        )
    if not batch.start_date <= payload.start_date <= payload.end_date <= batch.end_date:
        raise HTTPException(422, 'Semester dates must fall within the three-year Batch dates')
    previous = db.scalar(select(CohortSemester).where(
        CohortSemester.batch_id == batch.id,
        CohortSemester.semester_number == payload.semester_number - 1,
        CohortSemester.attempt_number == payload.attempt_number,
    )) if payload.semester_number > 1 else None
    if payload.semester_number > 1 and previous is None:
        raise HTTPException(422, f'Create Semester {payload.semester_number - 1} first')
    if previous is not None and payload.start_date <= previous.end_date:
        raise HTTPException(422, 'Semester dates must be sequential and non-overlapping')
    if db.scalar(
        select(CohortSemester.id).where(
            CohortSemester.batch_id == batch.id,
            CohortSemester.semester_number == payload.semester_number,
            CohortSemester.attempt_number == payload.attempt_number,
        )
    ):
        raise HTTPException(409, 'That cohort semester already exists')
    semester = CohortSemester(
        **payload.model_dump(),
        intake_id=level.intake_id,
        batch_id=level.batch_id,
    )
    db.add(semester)
    db.flush()
    log_audit(db, actor.id, 'cohort_semester.created', 'cohort_semester', semester.id, None, payload.model_dump(mode='json'))
    db.commit()
    db.refresh(semester)
    return _semester_read(db, semester)


@router.patch('/cohort-semesters/{semester_id}', response_model=CohortSemesterRead)
def update_cohort_semester(
    semester_id: int,
    payload: CohortSemesterUpdate,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    semester = db.get(CohortSemester, semester_id)
    if semester is None:
        raise HTTPException(404, 'Cohort semester not found')
    values = payload.model_dump(exclude_none=True)
    start_date = values.get('start_date', semester.start_date)
    end_date = values.get('end_date', semester.end_date)
    if start_date > end_date:
        raise HTTPException(422, 'Start date must be on or before end date')
    batch = db.get(Batch, semester.batch_id)
    if not batch.start_date <= start_date <= end_date <= batch.end_date:
        raise HTTPException(422, 'Semester dates must fall within the three-year Batch dates')
    previous = db.scalar(select(CohortSemester).where(
        CohortSemester.batch_id == semester.batch_id,
        CohortSemester.semester_number == semester.semester_number - 1,
        CohortSemester.attempt_number == semester.attempt_number,
    )) if semester.semester_number > 1 else None
    following = db.scalar(select(CohortSemester).where(
        CohortSemester.batch_id == semester.batch_id,
        CohortSemester.semester_number == semester.semester_number + 1,
        CohortSemester.attempt_number == semester.attempt_number,
    )) if semester.semester_number < 6 else None
    if previous is not None and start_date <= previous.end_date:
        raise HTTPException(422, 'Semester start must be after the previous Semester end')
    if following is not None and end_date >= following.start_date:
        raise HTTPException(422, 'Semester end must be before the next Semester start')
    for key, value in values.items():
        setattr(semester, key, value)
    log_audit(db, actor.id, 'cohort_semester.updated', 'cohort_semester', semester.id, None, values)
    db.commit()
    db.refresh(semester)
    return _semester_read(db, semester)


@router.post('/promotions/preview', response_model=PromotionPreviewRead)
def promotion_preview(payload: PromotionRequest, db: DbSession):
    try:
        source, target, students, errors = preview_promotion(db, **_promotion_kwargs(payload))
    except PromotionValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _preview_response(db, source, target, students, errors)


@router.post('/promotions', response_model=PromotionRunRead, status_code=201)
def create_promotion(
    payload: PromotionRequest,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    if not payload.preview_signature:
        raise HTTPException(422, 'Preview this promotion before applying it')
    try:
        run, students = apply_promotion(
            db,
            **_promotion_kwargs(payload),
            preview_signature=payload.preview_signature,
            created_by=actor.id,
            notes=payload.notes,
        )
        log_audit(
            db,
            actor.id,
            'promotion.applied',
            'promotion_run',
            run.id,
            None,
            {
                'source_cohort_semester_id': run.from_cohort_semester_id,
                'target_cohort_semester_id': run.to_cohort_semester_id,
                'total_students': len(students),
            },
        )
        db.commit()
        db.refresh(run)
    except PromotionValidationError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return _run_read(db, run)


@router.post('/section-placements/preview', response_model=PlacementPreviewRead)
def section_placement_preview(payload: PlacementRequest, db: DbSession):
    try:
        semester, students, errors = preview_initial_assignment(
            db,
            **_placement_kwargs(payload),
        )
    except PromotionValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    rows = [
        PromotionStudentRead(
            id=item.student.id,
            roll_number=item.student.roll_number,
            name=item.student.name,
            source_section_id=item.source_section_id,
            target_section_id=item.target_section_id,
            action=item.action,
            reason=item.reason,
        )
        for item in students
    ]
    return PlacementPreviewRead(
        semester=_semester_read(db, semester),
        total_students=len(rows),
        assign_count=sum(item.action == 'assign' for item in rows),
        hold_count=sum(item.action == 'hold' for item in rows),
        students=rows,
        errors=errors,
        preview_signature=placement_signature(semester, semester, students),
    )


@router.post('/section-placements', response_model=PlacementPreviewRead, status_code=201)
def apply_section_placement(
    payload: PlacementRequest,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    if not payload.preview_signature:
        raise HTTPException(422, 'Preview this Section assignment before applying it')
    try:
        semester, students = apply_initial_assignment(
            db,
            **_placement_kwargs(payload),
            preview_signature=payload.preview_signature,
        )
        log_audit(
            db,
            actor.id,
            'section_placement.applied',
            'cohort_semester',
            semester.id,
            None,
            {
                'assigned': sum(item.action == 'assign' for item in students),
                'held': sum(item.action == 'hold' for item in students),
                'strategy': payload.placement_strategy,
            },
        )
        db.commit()
    except PromotionValidationError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    rows = [
        PromotionStudentRead(
            id=item.student.id,
            roll_number=item.student.roll_number,
            name=item.student.name,
            source_section_id=item.source_section_id,
            target_section_id=item.target_section_id,
            action=item.action,
            reason=item.reason,
        )
        for item in students
    ]
    return PlacementPreviewRead(
        semester=_semester_read(db, semester),
        total_students=len(rows),
        assign_count=sum(item.action == 'assign' for item in rows),
        hold_count=sum(item.action == 'hold' for item in rows),
        students=rows,
        errors=[],
        preview_signature=payload.preview_signature,
    )


@router.post('/students/{student_id}/section-moves', response_model=EnrollmentHistoryRead, status_code=201)
def move_student(
    student_id: int,
    payload: SectionMoveRequest,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    try:
        enrollment = move_student_section(
            db,
            student_id=student_id,
            cohort_semester_id=payload.cohort_semester_id,
            target_section_id=payload.target_section_id,
            effective_date=payload.effective_date,
        )
        log_audit(
            db,
            actor.id,
            'student.section_moved',
            'student_enrollment',
            enrollment.id,
            None,
            payload.model_dump(mode='json'),
        )
        db.commit()
        db.refresh(enrollment)
        return enrollment
    except PromotionValidationError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get('/promotions', response_model=list[PromotionRunRead])
def promotion_runs(db: DbSession):
    runs = db.scalars(select(PromotionRun).order_by(PromotionRun.effective_date.desc())).all()
    return [_run_read(db, run) for run in runs]


@router.get('/promotions/{run_id}/students', response_model=list[PromotionRunStudentRead])
def promotion_run_students(run_id: int, db: DbSession):
    if db.get(PromotionRun, run_id) is None:
        raise HTTPException(404, 'Promotion run not found')
    items = db.scalars(
        select(PromotionRunItem)
        .where(PromotionRunItem.promotion_run_id == run_id)
        .order_by(PromotionRunItem.student_id)
    ).all()
    result = []
    for item in items:
        student = db.get(Student, item.student_id)
        if student is None:
            continue
        result.append(PromotionRunStudentRead(
            promotion_run_item_id=item.id,
            id=student.id,
            roll_number=student.roll_number,
            name=student.name,
            source_section_id=item.source_section_id,
            target_section_id=item.target_section_id,
            action=item.action,
            reason=item.reason,
        ))
    return result


@router.post('/promotions/{run_id}/students/{student_id}/release', response_model=PromotionRunRead)
def release_promotion_hold(
    run_id: int,
    student_id: int,
    payload: PromotionReleaseRequest,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    run = db.get(PromotionRun, run_id)
    if run is None:
        raise HTTPException(404, 'Promotion run not found')
    try:
        release_held_student(
            db,
            run,
            student_id,
            payload.target_section_id,
            payload.reason,
        )
        log_audit(
            db,
            actor.id,
            'promotion.hold_released',
            'promotion_run_item',
            student_id,
            {'status': 'hold'},
            {'status': 'promote', 'target_section_id': payload.target_section_id},
        )
        db.commit()
        db.refresh(run)
    except PromotionValidationError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return _run_read(db, run)


@router.get('/students/{student_id}/academic-history', response_model=list[EnrollmentHistoryRead])
def academic_history(student_id: int, db: DbSession):
    if db.get(Student, student_id) is None:
        raise HTTPException(404, 'Student not found')
    return db.scalars(
        select(StudentEnrollment)
        .where(StudentEnrollment.student_id == student_id)
        .order_by(StudentEnrollment.starts_on)
    ).all()
