import csv
import io
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func,select
from app.core.dependencies import DbSession,get_current_user,require_role,require_roles
from app.modules.academic.models import AcademicModule,ClassType,RoutineEntry,RoutineEntrySection,Section,Student,Subject,Teacher
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.identity.models import User
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
from .schemas import AttendanceClassType,AtRiskStudent,CollegeSummary,RiskRunResult,SectionStudentSummary,SectionSummary,SelectiveCandidate,StudentAttendanceDay,StudentAttendanceRecord,StudentAttendanceReport,StudentSummary,SubjectAttendance,TeacherAnalysisScope,TeacherAnalysisStudent,TeacherAttendanceAnalysis
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
    query=select(AttendanceRecord.class_session_id,AttendanceRecord.status,AttendanceRecord.check_in_time,ClassSession.session_date,TimetableEntry.subject_id,Subject.name,Subject.code,RoutineEntry.module_id,AcademicModule.title,AcademicModule.code,ClassType.id,ClassType.name,TimetableEntry.class_type).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).outerjoin(Subject,TimetableEntry.subject_id==Subject.id).outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id).outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id).outerjoin(ClassType,RoutineEntry.class_type_id==ClassType.id).where(AttendanceRecord.student_id==student.id,ClassSession.status==SessionStatus.COMPLETED)
    if date_from:query=query.where(ClassSession.session_date>=date_from)
    if date_to:query=query.where(ClassSession.session_date<=date_to)
    rows=db.execute(query.order_by(ClassSession.session_date.desc(),AttendanceRecord.class_session_id.desc())).all()
    subjects:dict[tuple[str,int],dict]={}; days:dict[date,dict]={}; records=[]
    for session_id,status,check_in_time,session_date,subject_id,subject_name,subject_code,module_id,module_title,module_code,class_type_id,class_type_name,legacy_class_type in rows:
        scope_id=module_id if module_id is not None else subject_id
        if scope_id is None:continue
        name=module_title or subject_name or "Unnamed subject"; code=module_code or subject_code; status_value=status.value if isinstance(status,AttendanceStatus) else str(status)
        record=StudentAttendanceRecord(session_id=session_id,date=session_date,weekday=session_date.strftime("%A"),subject_id=scope_id,subject_name=name,subject_code=code,class_type_id=class_type_id,class_type_name=class_type_name or legacy_class_type,status=status_value,check_in_time=check_in_time);records.append(record)
        key=("MODULE" if module_id is not None else "SUBJECT",scope_id);subject=subjects.setdefault(key,{"subject_id":scope_id,"subject_name":name,"present":0,"absent":0,"total":0});subject["total"]+=1
        attended=status in PASSING
        subject["present"]+=int(attended);subject["absent"]+=int(not attended)
        day=days.setdefault(session_date,{"date":session_date,"weekday":session_date.strftime("%A"),"present":0,"absent":0,"total":0,"records":[]});day["total"]+=1;day["present"]+=int(attended);day["absent"]+=int(not attended);day["records"].append(record)
    subject_items=[SubjectAttendance(**item,percentage=round(100*item["present"]/item["total"],2) if item["total"] else 0) for item in subjects.values()]
    day_items=[StudentAttendanceDay(**item,percentage=round(100*item["present"]/item["total"],2) if item["total"] else 0) for item in sorted(days.values(),key=lambda item:item["date"],reverse=True)]
    present=sum(item.present for item in subject_items);total=sum(item.total for item in subject_items);absent=total-present
    return StudentAttendanceReport(student_id=student.id,date_from=date_from,date_to=date_to,present=present,absent=absent,total=total,overall_percentage=round(100*present/total,2) if total else 0,subjects=sorted(subject_items,key=lambda item:item.subject_name.lower()),days=day_items,attendance_threshold_percent=settings.attendance_threshold_percent,minimum_observations=settings.minimum_observations)


def teacher_attendance_analysis_response(
    db: DbSession,
    teacher: Teacher,
    *,
    module_id: int | None,
    section_id: int | None,
    class_type_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> TeacherAttendanceAnalysis:
    """Summarise completed attendance for only classes a teacher is assigned to."""
    routines = db.scalars(select(RoutineEntry).where(RoutineEntry.teacher_id == teacher.id)).all()
    module_cache: dict[int, AcademicModule | None] = {}
    section_cache: dict[int, Section | None] = {}
    type_cache: dict[int, ClassType | None] = {}
    scopes: dict[tuple[int, int], TeacherAnalysisScope] = {}
    valid_class_types: set[int] = set()

    for routine in routines:
        module = module_cache.setdefault(routine.module_id, db.get(AcademicModule, routine.module_id))
        class_type = type_cache.setdefault(routine.class_type_id, db.get(ClassType, routine.class_type_id))
        valid_class_types.add(routine.class_type_id)
        routine_section_ids = {routine.section_id}
        routine_section_ids.update(db.scalars(select(RoutineEntrySection.section_id).where(RoutineEntrySection.routine_entry_id == routine.id)).all())
        for routine_section_id in routine_section_ids:
            section = section_cache.setdefault(routine_section_id, db.get(Section, routine_section_id))
            if module and section:
                scopes[(module.id, section.id)] = TeacherAnalysisScope(
                    module_id=module.id,
                    module_name=module.title,
                    module_code=module.code,
                    section_id=section.id,
                    section_name=section.name,
                )

    if module_id is not None and not any(scope.module_id == module_id for scope in scopes.values()):
        raise HTTPException(403, "This module is not assigned to you")
    if section_id is not None and not any(scope.section_id == section_id for scope in scopes.values()):
        raise HTTPException(403, "This section is not assigned to you")
    if module_id is not None and section_id is not None and (module_id, section_id) not in scopes:
        raise HTTPException(403, "This module is not assigned to the selected section")
    if class_type_id is not None and class_type_id not in valid_class_types:
        raise HTTPException(403, "This class type is not assigned to you")

    session_query = select(ClassSession).where(
        ClassSession.effective_teacher_id == teacher.id,
        ClassSession.status == SessionStatus.COMPLETED,
        ClassSession.routine_entry_id.is_not(None),
    )
    if date_from:
        session_query = session_query.where(ClassSession.session_date >= date_from)
    if date_to:
        session_query = session_query.where(ClassSession.session_date <= date_to)

    selected_sessions: list[ClassSession] = []
    selected_routines: dict[int, RoutineEntry] = {}
    for session in db.scalars(session_query.order_by(ClassSession.session_date.desc())).all():
        routine = next((item for item in routines if item.id == session.routine_entry_id), None)
        if not routine:
            continue
        if module_id is not None and routine.module_id != module_id:
            continue
        if class_type_id is not None and routine.class_type_id != class_type_id:
            continue
        if section_id is not None:
            routine_section_ids = {routine.section_id}
            routine_section_ids.update(db.scalars(select(RoutineEntrySection.section_id).where(RoutineEntrySection.routine_entry_id == routine.id)).all())
            if section_id not in routine_section_ids:
                continue
        selected_sessions.append(session)
        selected_routines[session.id] = routine

    available_class_types = [
        AttendanceClassType(class_type_id=type_id, class_type_name=type_cache[type_id].name if type_cache[type_id] else "Unnamed class type", present=0, absent=0, total=0, percentage=0)
        for type_id in sorted(valid_class_types, key=lambda value: (type_cache[value].name if type_cache[value] else "").lower())
    ]
    if not selected_sessions:
        return TeacherAttendanceAnalysis(
            teacher_id=teacher.id, date_from=date_from, date_to=date_to, present=0, absent=0, total=0, overall_percentage=0,
            scopes=sorted(scopes.values(), key=lambda scope: (scope.module_name.lower(), scope.section_name.lower())),
            available_class_types=available_class_types, students=[], class_types=[],
            attendance_threshold_percent=settings.attendance_threshold_percent, minimum_observations=settings.minimum_observations,
        )

    records = db.execute(
        select(AttendanceRecord, Student)
        .join(Student, AttendanceRecord.student_id == Student.id)
        .where(AttendanceRecord.class_session_id.in_([session.id for session in selected_sessions]))
    ).all()
    students: dict[int, dict] = {}
    class_types: dict[int, dict] = {}
    for record, student in records:
        if section_id is not None and student.section_id != section_id:
            continue
        routine = selected_routines[record.class_session_id]
        attended = record.status in PASSING
        student_item = students.setdefault(student.id, {
            "student_id": student.id, "student_name": student_display_name(student), "roll_number": student.roll_number,
            "present": 0, "absent": 0, "total": 0,
        })
        student_item["present" if attended else "absent"] += 1
        student_item["total"] += 1
        type_item = class_types.setdefault(routine.class_type_id, {
            "class_type_id": routine.class_type_id,
            "class_type_name": type_cache[routine.class_type_id].name if type_cache[routine.class_type_id] else "Unnamed class type",
            "present": 0, "absent": 0, "total": 0,
        })
        type_item["present" if attended else "absent"] += 1
        type_item["total"] += 1

    student_items: list[TeacherAnalysisStudent] = []
    for item in students.values():
        item["percentage"] = round(100 * item["present"] / item["total"], 2) if item["total"] else 0
        item["attendance_status"] = "building_baseline" if item["total"] < settings.minimum_observations else ("regular" if item["percentage"] >= settings.attendance_threshold_percent else "needs_attention")
        student_items.append(TeacherAnalysisStudent(**item))
    class_type_items = [
        AttendanceClassType(**item, percentage=round(100 * item["present"] / item["total"], 2) if item["total"] else 0)
        for item in class_types.values()
    ]
    present = sum(item.present for item in student_items)
    total = sum(item.total for item in student_items)
    return TeacherAttendanceAnalysis(
        teacher_id=teacher.id, date_from=date_from, date_to=date_to, present=present, absent=total - present, total=total,
        overall_percentage=round(100 * present / total, 2) if total else 0,
        scopes=sorted(scopes.values(), key=lambda scope: (scope.module_name.lower(), scope.section_name.lower())),
        available_class_types=available_class_types,
        students=sorted(student_items, key=lambda item: (item.percentage, item.student_name.lower())),
        class_types=sorted(class_type_items, key=lambda item: item.class_type_name.lower()),
        attendance_threshold_percent=settings.attendance_threshold_percent, minimum_observations=settings.minimum_observations,
    )
@router.get("/my-attendance-summary",response_model=StudentSummary)
def my_student_summary(user:Annotated[User,Depends(require_role("student"))],db:DbSession):
    return student_summary_response(db,current_student_profile(db,user))
@router.get("/my-attendance",response_model=StudentAttendanceReport)
def my_student_attendance(user:Annotated[User,Depends(require_role("student"))],db:DbSession,date_from:date|None=None,date_to:date|None=None):
    if date_from and date_to and date_from>date_to:raise HTTPException(422,"date_from must be on or before date_to")
    return student_attendance_report_response(db,current_student_profile(db,user),date_from,date_to)
@router.get("/teacher-attendance-analysis",response_model=TeacherAttendanceAnalysis)
def teacher_attendance_analysis(user:Annotated[User,Depends(require_role("teacher"))],db:DbSession,module_id:int|None=None,section_id:int|None=None,class_type_id:int|None=None,date_from:date|None=None,date_to:date|None=None):
    if date_from and date_to and date_from>date_to:raise HTTPException(422,"date_from must be on or before date_to")
    teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
    if not teacher:raise HTTPException(404,"Teacher profile not found")
    return teacher_attendance_analysis_response(db,teacher,module_id=module_id,section_id=section_id,class_type_id=class_type_id,date_from=date_from,date_to=date_to)
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
