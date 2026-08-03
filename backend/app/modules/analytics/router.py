from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.core.dependencies import DbSession,get_current_user,require_role,require_roles
from app.modules.academic.models import Section,Student,Subject
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.identity.models import User
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
from .schemas import RiskRunResult,SectionStudentSummary,SectionSummary,SelectiveCandidate,StudentSummary
from .service import PASSING,run_risk_evaluations,subject_stats
router=APIRouter(prefix="/analytics",tags=["analytics"])
@router.get("/students/{id}/attendance-summary",response_model=StudentSummary)
def student_summary(id:int,user:Annotated[User,Depends(get_current_user)],db:DbSession):
    student=db.scalar(select(Student).where(Student.user_id==user.id)) if user.role.value=="student" else db.get(Student,id)
    if not student:raise HTTPException(404,"Student not found")
    stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);total=sum(x["total"] for x in stats);return StudentSummary(student_id=student.id,overall_percentage=round(100*present/total,2) if total else 0,subjects=stats)
@router.get("/sections/{id}/attendance-summary",response_model=SectionSummary)
def section_summary(id:int,user:Annotated[User,Depends(require_roles("admin","teacher"))],db:DbSession):
    students=db.scalars(select(Student).where(Student.section_id==id)).all();items=[];all_present=all_total=0
    for student in students:
        stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);total=sum(x["total"] for x in stats);all_present+=present;all_total+=total;items.append(SectionStudentSummary(student_id=student.id,student_name=student.user.name,percentage=round(100*present/total,2) if total else 0))
    return SectionSummary(section_id=id,overall_percentage=round(100*all_present/all_total,2) if all_total else 0,students=items)
@router.get("/selective-absence",response_model=list[SelectiveCandidate])
def selective(date:date,batch_id:int,user:Annotated[User,Depends(require_roles("admin","teacher"))],db:DbSession):
    rows=db.execute(select(AttendanceRecord.student_id,AttendanceRecord.status,Subject.name).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).join(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).join(Subject,TimetableEntry.subject_id==Subject.id).join(Student,AttendanceRecord.student_id==Student.id).join(Section,Student.section_id==Section.id).where(ClassSession.session_date==date,ClassSession.status==SessionStatus.COMPLETED,Section.batch_id==batch_id)).all();groups={}
    for student_id,status,subject_name in rows:
        g=groups.setdefault(student_id,{"attended":[],"missed":[]});g["attended" if status in PASSING else "missed"].append(subject_name)
    return [SelectiveCandidate(student_id=sid,date=date,attended_subjects=g["attended"],missed_subjects=g["missed"]) for sid,g in groups.items() if g["attended"] and g["missed"]]
@router.post("/risk-evaluations/run",response_model=RiskRunResult)
def run(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return run_risk_evaluations(db)
