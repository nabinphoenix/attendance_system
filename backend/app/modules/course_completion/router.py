from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.modules.academic.models import ModuleOffering, Student, StudentSubjectEnrollment, Subject
from app.modules.identity.models import User
from app.modules.operations.service import log_audit, queue_notification
from app.modules.scheduling.models import OverrideStatus, ScheduleOverride
from app.modules.scheduling.service import (
    create_schedule_override,
    routine_section_ids,
    validate_routine_override_conflicts,
)

from .models import CoursePlan, MakeupSuggestion, SuggestionStatus
from .schemas import PlanCreate, PlanRead, SuggestionDecision, SuggestionRead
from .service import find_makeup_slot

router = APIRouter(
    prefix="/course-completion",
    tags=["course completion"],
    dependencies=[Depends(require_role("admin"))],
)


def plan_read(plan: CoursePlan) -> PlanRead:
    return PlanRead(
        id=plan.id,
        subject_id=plan.subject_id,
        module_offering_id=plan.module_offering_id,
        batch_id=plan.batch_id,
        planned_sessions=plan.planned_sessions,
        conducted_sessions=plan.conducted_sessions,
        deficit=plan.planned_sessions - plan.conducted_sessions,
    )


def validate_plan_source(db: DbSession, payload: PlanCreate) -> None:
    if payload.module_offering_id:
        offering = db.get(ModuleOffering, payload.module_offering_id)
        if not offering:
            raise HTTPException(404, "Module offering not found")
        if offering.batch_id != payload.batch_id:
            raise HTTPException(422, "Module offering must belong to the selected batch")
        return
    subject = db.get(Subject, payload.subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")
    if subject.section.batch_id != payload.batch_id:
        raise HTTPException(422, "Subject must belong to the selected batch")


@router.post("/plans", response_model=PlanRead)
def create_plan(payload: PlanCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    validate_plan_source(db, payload)
    source_filter = (
        CoursePlan.module_offering_id == payload.module_offering_id
        if payload.module_offering_id
        else CoursePlan.subject_id == payload.subject_id
    )
    if db.scalar(select(CoursePlan.id).where(source_filter, CoursePlan.batch_id == payload.batch_id)):
        raise HTTPException(409, "A course plan already exists for this course and batch")
    plan = CoursePlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    log_audit(db, user.id, "course_plan.created", "course_plan", plan.id, None, payload.model_dump())
    db.commit()
    db.refresh(plan)
    return plan_read(plan)


@router.get("/plans", response_model=list[PlanRead])
def plans(
    db: DbSession,
    batch_id: int | None = None,
    subject_id: int | None = None,
    module_offering_id: int | None = None,
):
    query = select(CoursePlan)
    if batch_id:
        query = query.where(CoursePlan.batch_id == batch_id)
    if subject_id:
        query = query.where(CoursePlan.subject_id == subject_id)
    if module_offering_id:
        query = query.where(CoursePlan.module_offering_id == module_offering_id)
    return [plan_read(plan) for plan in db.scalars(query).all()]


@router.post("/plans/{id}/suggest-makeup", response_model=SuggestionRead)
def suggest(id: int, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    if not db.get(CoursePlan, id):
        raise HTTPException(404, "Course plan not found")
    slot = find_makeup_slot(db, id)
    if not slot:
        raise HTTPException(404, "No conflict-free slot found in the next 14 days")
    suggestion = MakeupSuggestion(
        course_plan_id=id,
        suggested_date=slot["date"],
        suggested_start_time=slot["start_time"],
        suggested_room=slot["room"],
        teacher_id=slot["teacher_id"],
        timetable_entry_id=slot["timetable_entry_id"],
        routine_entry_id=slot["routine_entry_id"],
    )
    db.add(suggestion)
    db.flush()
    log_audit(db, user.id, "makeup_suggestion.created", "makeup_suggestion", suggestion.id, None, slot)
    db.commit()
    db.refresh(suggestion)
    return suggestion


@router.patch("/suggestions/{id}", response_model=SuggestionRead)
def decide(id: int, payload: SuggestionDecision, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    suggestion = db.get(MakeupSuggestion, id)
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    if suggestion.status != SuggestionStatus.PENDING:
        raise HTTPException(409, "Suggestion has already been decided")
    try:
        suggestion.status = SuggestionStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(422, "Status must be approved or rejected") from exc
    if suggestion.status == SuggestionStatus.PENDING:
        raise HTTPException(422, "Choose approved or rejected")
    if suggestion.status == SuggestionStatus.APPROVED:
        end_time = (datetime.combine(suggestion.suggested_date, suggestion.suggested_start_time) + timedelta(hours=1)).time()
        if suggestion.routine_entry_id:
            entry = suggestion.routine_entry
            proposed = ScheduleOverride(
                routine_entry_id=entry.id,
                override_date=suggestion.suggested_date,
                created_by=user.id,
                reason=f"Approved makeup for course plan {suggestion.course_plan_id}",
                new_teacher_id=suggestion.teacher_id,
                new_room=suggestion.suggested_room,
                start_time=suggestion.suggested_start_time,
                end_time=end_time,
                is_makeup=True,
                status=OverrideStatus.APPROVED,
            )
            validate_routine_override_conflicts(db, entry, proposed)
            override = create_schedule_override(
                db,
                routine_entry_id=entry.id,
                override_date=suggestion.suggested_date,
                created_by=user.id,
                reason=proposed.reason,
                new_teacher_id=suggestion.teacher_id,
                new_room=suggestion.suggested_room,
                start_time=suggestion.suggested_start_time,
                end_time=end_time,
                is_makeup=True,
                status=OverrideStatus.APPROVED,
            )
            students = db.scalars(select(Student).where(Student.section_id.in_(routine_section_ids(db, entry)))).all()
        else:
            override = create_schedule_override(
                db,
                timetable_entry_id=suggestion.timetable_entry_id,
                override_date=suggestion.suggested_date,
                created_by=user.id,
                reason=f"Approved makeup for course plan {suggestion.course_plan_id}",
                new_teacher_id=suggestion.teacher_id,
                new_room=suggestion.suggested_room,
                start_time=suggestion.suggested_start_time,
                end_time=end_time,
                status=OverrideStatus.APPROVED,
            )
            plan = db.get(CoursePlan, suggestion.course_plan_id)
            students = db.scalars(
                select(Student)
                .join(StudentSubjectEnrollment)
                .where(StudentSubjectEnrollment.subject_id == plan.subject_id)
            ).all()
        suggestion.approved_by = user.id
        for student in students:
            queue_notification(
                db,
                "student",
                student.id,
                "Makeup class scheduled",
                f"A makeup class is scheduled on {suggestion.suggested_date} at {suggestion.suggested_start_time} in {suggestion.suggested_room}.",
                "schedule_override",
                override.id,
            )
        queue_notification(
            db,
            "teacher",
            suggestion.teacher_id,
            "Makeup class scheduled",
            f"Your makeup class is scheduled on {suggestion.suggested_date} at {suggestion.suggested_start_time} in {suggestion.suggested_room}.",
            "schedule_override",
            override.id,
        )
        log_audit(db, user.id, "makeup_suggestion.approved", "makeup_suggestion", suggestion.id, {"status": "pending"}, {"status": "approved", "override_id": override.id})
    else:
        log_audit(db, user.id, "makeup_suggestion.rejected", "makeup_suggestion", suggestion.id, {"status": "pending"}, {"status": "rejected"})
    db.commit()
    db.refresh(suggestion)
    return suggestion
