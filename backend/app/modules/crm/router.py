from datetime import UTC,datetime
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.core.dependencies import DbSession,require_roles
from app.modules.identity.models import User
from .models import CaseInteraction,CaseStatus,StudentCase
from .schemas import Assignment,CaseDetail,CaseRead,InteractionCreate,InteractionRead,StatusChange
from app.modules.operations.service import log_audit,queue_notification
router=APIRouter(prefix="/cases",tags=["crm"])
Staff=Annotated[User,Depends(require_roles("admin","coordinator"))]
@router.get("",response_model=list[CaseRead])
def cases(user:Staff,db:DbSession,status:str|None=None,assigned_to:int|None=None,student_id:int|None=None):
    q=select(StudentCase)
    if status:q=q.where(StudentCase.status==CaseStatus(status))
    if assigned_to:q=q.where(StudentCase.assigned_to==assigned_to)
    if student_id:q=q.where(StudentCase.student_id==student_id)
    return db.scalars(q.order_by(StudentCase.opened_at.desc())).all()
@router.get("/{id}",response_model=CaseDetail)
def detail(id:int,user:Staff,db:DbSession):
    case=db.get(StudentCase,id)
    if not case:raise HTTPException(404,"Case not found")
    case.interactions.sort(key=lambda x:x.logged_at);return case
@router.patch("/{id}/assign",response_model=CaseRead)
def assign(id:int,p:Assignment,user:Staff,db:DbSession):
    case=db.get(StudentCase,id)
    if not case:raise HTTPException(404,"Case not found")
    before=case.assigned_to;case.assigned_to=p.assigned_to;queue_notification(db,"admin",p.assigned_to,"Case assigned",f"Student case #{case.id} has been assigned to you.","case",case.id);log_audit(db,user.id,"case.assigned","student_case",case.id,{"assigned_to":before},{"assigned_to":p.assigned_to});db.commit();db.refresh(case);return case
@router.post("/{id}/interactions",response_model=InteractionRead)
def interact(id:int,p:InteractionCreate,user:Staff,db:DbSession):
    if not db.get(StudentCase,id):raise HTTPException(404,"Case not found")
    obj=CaseInteraction(case_id=id,staff_id=user.id,**p.model_dump());db.add(obj);db.flush();log_audit(db,user.id,"case.interaction_created","case_interaction",obj.id,None,{"case_id":id,"channel":p.channel});db.commit();db.refresh(obj);return obj
@router.patch("/{id}/status",response_model=CaseRead)
def change_status(id:int,p:StatusChange,user:Staff,db:DbSession):
    case=db.get(StudentCase,id)
    if not case:raise HTTPException(404,"Case not found")
    try:new=CaseStatus(p.status)
    except ValueError as exc:raise HTTPException(422,"Invalid case status") from exc
    if new==CaseStatus.CLOSED and not (p.note and p.note.strip()):raise HTTPException(422,"A closing note is required")
    before=case.status.value
    if p.note:db.add(CaseInteraction(case_id=id,staff_id=user.id,channel="note",notes=p.note,outcome=f"Status changed to {new.value}"))
    case.status=new;case.closed_at=datetime.now(UTC) if new==CaseStatus.CLOSED else None;log_audit(db,user.id,"case.status_changed","student_case",case.id,{"status":before},{"status":new.value,"note":p.note});db.commit();db.refresh(case);return case
