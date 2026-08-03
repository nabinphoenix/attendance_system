from datetime import datetime,timedelta
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.core.dependencies import DbSession,require_role
from app.modules.identity.models import User
from app.modules.scheduling.models import OverrideStatus
from app.modules.scheduling.service import create_schedule_override
from .models import CoursePlan,MakeupSuggestion,SuggestionStatus
from .schemas import PlanCreate,PlanRead,SuggestionDecision,SuggestionRead
from .service import find_makeup_slot
from app.modules.operations.service import log_audit,queue_notification
from app.modules.academic.models import Student,StudentSubjectEnrollment
router=APIRouter(prefix="/course-completion",tags=["course completion"],dependencies=[Depends(require_role("admin"))])
def plan_read(p):return PlanRead(id=p.id,subject_id=p.subject_id,batch_id=p.batch_id,planned_sessions=p.planned_sessions,conducted_sessions=p.conducted_sessions,deficit=p.planned_sessions-p.conducted_sessions)
@router.post("/plans",response_model=PlanRead)
def create_plan(p:PlanCreate,db:DbSession):obj=CoursePlan(**p.model_dump());db.add(obj);db.commit();db.refresh(obj);return plan_read(obj)
@router.get("/plans",response_model=list[PlanRead])
def plans(db:DbSession,batch_id:int|None=None,subject_id:int|None=None):
    q=select(CoursePlan)
    if batch_id:q=q.where(CoursePlan.batch_id==batch_id)
    if subject_id:q=q.where(CoursePlan.subject_id==subject_id)
    return [plan_read(x) for x in db.scalars(q).all()]
@router.post("/plans/{id}/suggest-makeup",response_model=SuggestionRead)
def suggest(id:int,db:DbSession):
    slot=find_makeup_slot(db,id)
    if not slot:raise HTTPException(404,"No conflict-free slot found in the next 14 days")
    obj=MakeupSuggestion(course_plan_id=id,suggested_date=slot["date"],suggested_start_time=slot["start_time"],suggested_room=slot["room"],teacher_id=slot["teacher_id"],timetable_entry_id=slot["timetable_entry_id"]);db.add(obj);db.commit();db.refresh(obj);return obj
@router.patch("/suggestions/{id}",response_model=SuggestionRead)
def decide(id:int,p:SuggestionDecision,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=db.get(MakeupSuggestion,id)
    if not obj:raise HTTPException(404,"Suggestion not found")
    try:obj.status=SuggestionStatus(p.status)
    except ValueError as exc:raise HTTPException(422,"Status must be approved or rejected") from exc
    if obj.status==SuggestionStatus.PENDING:raise HTTPException(422,"Choose approved or rejected")
    if obj.status==SuggestionStatus.APPROVED:
        obj.approved_by=user.id;start_dt=datetime.combine(obj.suggested_date,obj.suggested_start_time);override=create_schedule_override(db,timetable_entry_id=obj.timetable_entry_id,override_date=obj.suggested_date,created_by=user.id,reason=f"Approved makeup for course plan {obj.course_plan_id}",new_teacher_id=obj.teacher_id,new_room=obj.suggested_room,start_time=obj.suggested_start_time,end_time=(start_dt+timedelta(hours=1)).time(),status=OverrideStatus.APPROVED);plan=db.get(CoursePlan,obj.course_plan_id)
        for student in db.scalars(select(Student).join(StudentSubjectEnrollment).where(StudentSubjectEnrollment.subject_id==plan.subject_id)).all():queue_notification(db,"student",student.id,"Makeup class scheduled",f"A makeup class is scheduled on {obj.suggested_date} at {obj.suggested_start_time} in {obj.suggested_room}.","schedule_override",override.id)
        queue_notification(db,"teacher",obj.teacher_id,"Makeup class scheduled",f"Your makeup class is scheduled on {obj.suggested_date} at {obj.suggested_start_time} in {obj.suggested_room}.","schedule_override",override.id);log_audit(db,user.id,"makeup_suggestion.approved","makeup_suggestion",obj.id,{"status":"pending"},{"status":"approved","override_id":override.id})
    db.commit();db.refresh(obj);return obj
