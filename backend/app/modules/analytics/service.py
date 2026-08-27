from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.academic.models import AcademicModule, Guardian, RoutineEntry, Student, Subject
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.crm.service import get_or_create_attendance_case
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
from app.modules.operations.service import queue_notification
PASSING=(AttendanceStatus.PRESENT,AttendanceStatus.LATE)
def subject_stats(db:Session,student_id:int)->list[dict]:
    """Return attendance by legacy subject or canonical academic module."""
    rows=db.execute(
        select(
            AttendanceRecord.status,
            TimetableEntry.subject_id,
            Subject.name,
            RoutineEntry.module_id,
            AcademicModule.title,
        )
        .join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id)
        .outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id)
        .outerjoin(Subject,TimetableEntry.subject_id==Subject.id)
        .outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id)
        .outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id)
        .where(AttendanceRecord.student_id==student_id,ClassSession.status==SessionStatus.COMPLETED)
    ).all();groups={}
    for status,subject_id,subject_name,module_id,module_title in rows:
        scope_type,scope_id,name=("MODULE",module_id,module_title) if module_id else ("SUBJECT",subject_id,subject_name)
        g=groups.setdefault((scope_type,scope_id),{"subject_id":scope_id,"subject_name":name,"scope_type":scope_type,"scope_id":scope_id,"present":0,"absent":0,"total":0});g["total"]+=1
        if status in PASSING:g["present"]+=1
        else:g["absent"]+=1
    for g in groups.values():g["percentage"]=round(100*g["present"]/g["total"],2) if g["total"] else 0
    return list(groups.values())
def run_risk_evaluations(db:Session)->dict:
    evaluated=triggered=created=updated=0
    students=db.scalars(select(Student)).all()
    for student in students:
        for stat in subject_stats(db,student.id):
            evaluated+=1
            if stat["total"]>=settings.minimum_observations and stat["percentage"]<settings.attendance_threshold_percent:
                triggered+=1;case,was_created=get_or_create_attendance_case(db,student.id,stat["scope_type"],stat["scope_id"],stat["percentage"]);created+=was_created;updated+=not was_created
                if was_created:
                    for guardian in db.scalars(select(Guardian).where(Guardian.student_id==student.id)).all():queue_notification(db,"guardian",guardian.id,"Attendance support alert",f"Your ward's attendance in {stat['subject_name']} has dropped below {settings.attendance_threshold_percent}%. Our team will be in touch.","case",case.id)
    db.commit();return {"evaluated":evaluated,"triggered":triggered,"created":created,"updated":updated}
