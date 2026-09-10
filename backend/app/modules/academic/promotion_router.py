from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, func, select

from app.core.dependencies import DbSession, require_role
from app.modules.identity.models import User
from app.modules.operations.service import log_audit

from .models import Batch, CohortSemester, Intake, PromotionRun, PromotionRunItem, Student, StudentEnrollment
from .promotion_service import (
    PromotionValidationError,
    apply_promotion,
    preview_promotion,
    release_held_student,
)


class CohortSemesterCreate(BaseModel):
    intake_id: int
    batch_id: int
    semester_number: int = Field(ge=1)
    attempt_number: int = Field(default=1, ge=1)
    start_date: date
    end_date: date
    status: str = 'planned'


class CohortSemesterRead(CohortSemesterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PromotionRequest(BaseModel):
    intake_id: int
    batch_id: int
    from_cohort_semester_id: int
    to_cohort_semester_id: int
    effective_date: date
    section_mapping: dict[int, int] = Field(default_factory=dict)
    hold_student_ids: list[int] = Field(default_factory=list)
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


router = APIRouter(
    prefix='/academic',
    tags=['academic-promotions'],
    dependencies=[Depends(require_role('admin'))],
)


def _semester_read(semester: CohortSemester) -> CohortSemesterRead:
    return CohortSemesterRead.model_validate(semester)


def _preview_response(source, target, students, errors) -> PromotionPreviewRead:
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
        source=_semester_read(source),
        target=_semester_read(target),
        total_students=len(rows),
        promote_count=sum(row.action == 'promote' for row in rows),
        hold_count=sum(row.action == 'hold' for row in rows),
        students=rows,
        errors=errors,
    )


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
    return db.scalars(
        select(CohortSemester).order_by(
            CohortSemester.start_date,
            CohortSemester.intake_id,
            CohortSemester.batch_id,
            CohortSemester.semester_number,
        )
    ).all()


@router.post('/cohort-semesters', response_model=CohortSemesterRead, status_code=201)
def create_cohort_semester(
    payload: CohortSemesterCreate,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    if payload.start_date > payload.end_date:
        raise HTTPException(422, 'Start date must be on or before end date')
    intake = db.get(Intake, payload.intake_id)
    batch = db.get(Batch, payload.batch_id)
    if intake is None or batch is None:
        raise HTTPException(404, 'Intake or batch not found')
    if intake.program_id != batch.program_id:
        raise HTTPException(422, 'Intake and batch must belong to the same program')
    if db.scalar(
        select(CohortSemester.id).where(
            CohortSemester.intake_id == payload.intake_id,
            CohortSemester.batch_id == payload.batch_id,
            CohortSemester.semester_number == payload.semester_number,
            CohortSemester.attempt_number == payload.attempt_number,
        )
    ):
        raise HTTPException(409, 'That cohort semester already exists')
    semester = CohortSemester(**payload.model_dump())
    db.add(semester)
    db.flush()
    log_audit(db, actor.id, 'cohort_semester.created', 'cohort_semester', semester.id, None, payload.model_dump(mode='json'))
    db.commit()
    db.refresh(semester)
    return semester


@router.post('/promotions/preview', response_model=PromotionPreviewRead)
def promotion_preview(payload: PromotionRequest, db: DbSession):
    try:
        source, target, students, errors = preview_promotion(
            db,
            **payload.model_dump(exclude={'notes', 'hold_student_ids'}),
            hold_student_ids=set(payload.hold_student_ids),
        )
    except PromotionValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _preview_response(source, target, students, errors)


@router.post('/promotions', response_model=PromotionRunRead, status_code=201)
def create_promotion(
    payload: PromotionRequest,
    actor: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    try:
        run, students = apply_promotion(
            db,
            **payload.model_dump(exclude={'notes', 'hold_student_ids'}),
            hold_student_ids=set(payload.hold_student_ids),
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


@router.get('/promotions', response_model=list[PromotionRunRead])
def promotion_runs(db: DbSession):
    runs = db.scalars(select(PromotionRun).order_by(PromotionRun.effective_date.desc())).all()
    return [_run_read(db, run) for run in runs]


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
