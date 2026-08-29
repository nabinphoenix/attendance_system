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
from .schemas import AtRiskStudent,CollegeSummary,RiskRunResult,SectionStudentSummary,SectionSummary,SelectiveCandidate,StudentAttendanceDay,StudentAttendanceRecord,StudentAttendanceReport,StudentSummary,SubjectAttendance
from .service import PASSING,run_risk_evaluations,subject_stats
from app.core.config import settings
from app.modules.crm.models import CaseStatus,StudentCase
from app.modules.scheduling.models import OverrideStatus,ScheduleOverride
from app.modules.course_completion.models import MakeupSuggestion,SuggestionStatus
from app.modules.academic.student_profile_service import current_student_profile
router=APIRouter(prefix="/analytics",tags=["analytics"])
def student_display_name(student:Student)->str:
    return student.user.name if student.user else student.name or student.roll_number
def student_summary_response(db:DbSession,student:Student)->StudentSummary:
    stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);absent=sum(x["absent"] for x in stats);total=sum(x["total"] for x in stats)
    return StudentSummary(student_id=student.id,present=present,absent=absent,total=total,overall_percentage=round(100*present/total,2) if total else 0,subjects=stats,attendance_threshold_percent=settings.attendance_threshold_percent,minimum_observations=settings.minimum_observations)
def student_attendance_report_response(db:DbSession,student:Student,date_from:date|None,date_to:date|None)->StudentAttendanceReport:
    query=select(AttendanceRecord.class_session_id,AttendanceRecord.status,AttendanceRecord.check_in_time,ClassSession.session_date,TimetableEntry.subject_id,Subject.name,Subject.code,RoutineEntry.module_id,AcademicModule.title,AcademicModule.code).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).outerjoin(Subject,TimetableEntry.subject_id==Subject.id).outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id).outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id).where(AttendanceRecord.student_id==student.id,ClassSession.status==SessionStatus.COMPLETED)
    if date_from:query=query.where(ClassSession.session_date>=date_from)
    if date_to:query=query.where(ClassSession.session_date<=date_to)
    rows=db.execute(query.order_by(ClassSession.session_date.desc(),AttendanceRecord.class_session_id.desc())).all()
    subjects:dict[tuple[str,int],dict]={}; days:dict[date,dict]={}; records=[]
    for session_id,status,check_in_time,session_date,subject_id,subject_name,subject_code,module_id,module_title,module_code in rows:
        scope_id=module_id if module_id is not None else subject_id
        if scope_id is None:continue
        name=module_title or subject_name or "Unnamed subject"; code=module_code or subject_code; status_value=status.value if isinstance(status,AttendanceStatus) else str(status)
        record=StudentAttendanceRecord(session_id=session_id,date=session_date,weekday=session_date.strftime("%A"),subject_id=scope_id,subject_name=name,subject_code=code,status=status_value,check_in_time=check_in_time);records.append(record)
        key=("MODULE" if module_id is not None else "SUBJECT",scope_id);subject=subjects.setdefault(key,{"subject_id":scope_id,"subject_name":name,"present":0,"absent":0,"total":0});subject["total"]+=1
        attended=status in PASSING
        subject["present"]+=int(attended);subject["absent"]+=int(not attended)
        day=days.setdefault(session_date,{"date":session_date,"weekday":session_date.strftime("%A"),"present":0,"absent":0,"total":0,"records":[]});day["total"]+=1;day["present"]+=int(attended);day["absent"]+=int(not attended);day["records"].append(record)
    subject_items=[SubjectAttendance(**item,percentage=round(100*item["present"]/item["total"],2) if item["total"] else 0) for item in subjects.values()]
    day_items=[StudentAttendanceDay(**item,percentage=round(100*item["present"]/item["total"],2) if item["total"] else 0) for item in sorted(days.values(),key=lambda item:item["date"],reverse=True)]
    present=sum(item.present for item in subject_items);total=sum(item.total for item in subject_items);absent=total-present
    return StudentAttendanceReport(student_id=student.id,date_from=date_from,date_to=date_to,present=present,absent=absent,total=total,overall_percentage=round(100*present/total,2) if total else 0,subjects=sorted(subject_items,key=lambda item:item.subject_name.lower()),days=day_items,attendance_threshold_percent=settings.attendance_threshold_percent,minimum_observations=settings.minimum_observations)
@router.get("/my-attendance-summary",response_model=StudentSummary)
def my_student_summary(user:Annotated[User,Depends(require_role("student"))],db:DbSession):
    return student_summary_response(db,current_student_profile(db,user))
@router.get("/my-attendance",response_model=StudentAttendanceReport)
def my_student_attendance(user:Annotated[User,Depends(require_role("student"))],db:DbSession,date_from:date|None=None,date_to:date|None=None):
    if date_from and date_to and date_from>date_to:raise HTTPException(422,"date_from must be on or before date_to")
    return student_attendance_report_response(db,current_student_profile(db,user),date_from,date_to)
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
        stats=subject_stats(db,student.id);present=sum(x["present"] for x in stats);total=sum(x["total"] for x in stats);all_present+=present;all_total+=total;items.append(SectionStudentSummary(student_id=student.id,student_name=student_display_name(student),percentage=round(100*present/total,2) if total else 0))
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
                case=db.scalar(select(StudentCase).where(StudentCase.student_id==student.id,StudentCase.scope_type==stat["scope_type"],StudentCase.scope_id==stat["scope_id"],StudentCase.status.in_([CaseStatus.OPEN,CaseStatus.IN_PROGRESS])));result.append(AtRiskStudent(student_id=student.id,student_name=student_display_name(student),subject_id=stat["scope_id"],subject_name=stat["subject_name"],attendance_percentage=stat["percentage"],observations=stat["total"],case_status=case.status.value if case else None))
    return result
