import csv
import io
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func,select
from app.core.dependencies import DbSession,get_current_user,require_role,require_roles
from app.modules.academic.models import AcademicModule,RoutineEntry,Section,Student,Subject
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.identity.models import User
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
from .schemas import AtRiskStudent,CollegeSummary,RiskRunResult,SectionStudentSummary,SectionSummary,SelectiveCandidate,StudentSummary
from .service import PASSING,run_risk_evaluations,subject_stats
from app.core.config import settings
from app.modules.crm.models import CaseStatus,StudentCase
from app.modules.scheduling.models import OverrideStatus,ScheduleOverride
from app.modules.course_completion.models import MakeupSuggestion,SuggestionStatus
from app.modules.academic.student_profile_service import current_student_profile
router=APIRouter(prefix="/analytics",tags=["analytics"])
def student_summary_response(db:DbSession,student:Student)->StudentSummary:
    stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);absent=sum(x["absent"] for x in stats);total=sum(x["total"] for x in stats)
    return StudentSummary(student_id=student.id,present=present,absent=absent,total=total,overall_percentage=round(100*present/total,2) if total else 0,subjects=stats,attendance_threshold_percent=settings.attendance_threshold_percent,minimum_observations=settings.minimum_observations)
@router.get("/my-attendance-summary",response_model=StudentSummary)
def my_student_summary(user:Annotated[User,Depends(require_role("student"))],db:DbSession):
    return student_summary_response(db,current_student_profile(db,user))
@router.get("/my-attendance-summary.csv")
def my_student_summary_csv(user:Annotated[User,Depends(require_role("student"))],db:DbSession):
    summary=student_summary_response(db,current_student_profile(db,user));output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["Subject","Present","Absent","Total classes","Attendance percentage"])
    for subject in sorted(summary.subjects,key=lambda item:item.subject_name.lower()):writer.writerow([subject.subject_name,subject.present,subject.absent,subject.total,subject.percentage])
    writer.writerow([]);writer.writerow(["Overall",summary.present,summary.absent,summary.total,summary.overall_percentage])
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":'attachment; filename="my_attendance_analysis.csv"'})
@router.get("/students/{id}/attendance-summary",response_model=StudentSummary)
def student_summary(id:int,user:Annotated[User,Depends(get_current_user)],db:DbSession):
    student=current_student_profile(db,user) if user.role.value=="student" else db.get(Student,id)
    if not student:raise HTTPException(404,"Student not found")
    return student_summary_response(db,student)
@router.get("/sections/{id}/attendance-summary",response_model=SectionSummary)
def section_summary(id:int,user:Annotated[User,Depends(require_roles("admin","teacher"))],db:DbSession):
    students=db.scalars(select(Student).where(Student.section_id==id)).all();items=[];all_present=all_total=0
    for student in students:
        stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);total=sum(x["total"] for x in stats);all_present+=present;all_total+=total;items.append(SectionStudentSummary(student_id=student.id,student_name=student.user.name,percentage=round(100*present/total,2) if total else 0))
    return SectionSummary(section_id=id,overall_percentage=round(100*all_present/all_total,2) if all_total else 0,students=items)
@router.get("/selective-absence",response_model=list[SelectiveCandidate])
def selective(date:date,batch_id:int,user:Annotated[User,Depends(require_roles("admin","teacher"))],db:DbSession):
    rows=db.execute(select(AttendanceRecord.student_id,AttendanceRecord.status,Subject.name,AcademicModule.title).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).outerjoin(Subject,TimetableEntry.subject_id==Subject.id).outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id).outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id).join(Student,AttendanceRecord.student_id==Student.id).join(Section,Student.section_id==Section.id).where(ClassSession.session_date==date,ClassSession.status==SessionStatus.COMPLETED,Section.batch_id==batch_id)).all();groups={}
    for student_id,status,subject_name,module_title in rows:
        g=groups.setdefault(student_id,{"attended":[],"missed":[]});g["attended" if status in PASSING else "missed"].append(module_title or subject_name)
    return [SelectiveCandidate(student_id=sid,date=date,attended_subjects=g["attended"],missed_subjects=g["missed"]) for sid,g in groups.items() if g["attended"] and g["missed"]]
@router.post("/risk-evaluations/run",response_model=RiskRunResult)
def run(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return run_risk_evaluations(db)
@router.get("/college-summary",response_model=CollegeSummary)
def college_summary(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    records=db.scalars(select(AttendanceRecord).join(ClassSession).where(ClassSession.status==SessionStatus.COMPLETED)).all();passing=sum(r.status in PASSING for r in records);counts={"low":0,"medium":0,"high":0}
    for priority,count in db.execute(select(StudentCase.priority,func.count()).where(StudentCase.status.in_([CaseStatus.OPEN,CaseStatus.IN_PROGRESS])).group_by(StudentCase.priority)).all():counts[priority.value]=count
    return CollegeSummary(attendance_percentage=round(100*passing/len(records),2) if records else 0,open_cases_by_priority=counts,pending_overrides=db.scalar(select(func.count()).select_from(ScheduleOverride).where(ScheduleOverride.status==OverrideStatus.PENDING)) or 0,pending_makeup_suggestions=db.scalar(select(func.count()).select_from(MakeupSuggestion).where(MakeupSuggestion.status==SuggestionStatus.PENDING)) or 0)
@router.get("/at-risk-students",response_model=list[AtRiskStudent])
def at_risk(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    result=[]
    for student in db.scalars(select(Student)).all():
        for stat in subject_stats(db,student.id):
            if stat["total"]>=settings.minimum_observations and stat["percentage"]<settings.attendance_threshold_percent:
                case=db.scalar(select(StudentCase).where(StudentCase.student_id==student.id,StudentCase.scope_type==stat["scope_type"],StudentCase.scope_id==stat["scope_id"],StudentCase.status.in_([CaseStatus.OPEN,CaseStatus.IN_PROGRESS])));result.append(AtRiskStudent(student_id=student.id,student_name=student.user.name,subject_id=stat["scope_id"],subject_name=stat["subject_name"],attendance_percentage=stat["percentage"],observations=stat["total"],case_status=case.status.value if case else None))
    return result
