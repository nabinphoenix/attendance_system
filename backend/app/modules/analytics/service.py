from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.academic.models import AcademicModule, ClassType, Guardian, RoutineEntry, Student, Subject
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
            Subject.code,
            RoutineEntry.module_id,
            AcademicModule.title,
            AcademicModule.code,
            ClassType.name,
            TimetableEntry.class_type,
        )
        .join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id)
        .outerjoin(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id)
        .outerjoin(Subject,TimetableEntry.subject_id==Subject.id)
        .outerjoin(RoutineEntry,ClassSession.routine_entry_id==RoutineEntry.id)
        .outerjoin(AcademicModule,RoutineEntry.module_id==AcademicModule.id)
        .outerjoin(ClassType,RoutineEntry.class_type_id==ClassType.id)
        .where(AttendanceRecord.student_id==student_id,ClassSession.status==SessionStatus.COMPLETED)
    ).all();groups={}
    for status,subject_id,subject_name,subject_code,module_id,module_title,module_code,class_type_name,legacy_class_type in rows:
        scope_type,scope_id,name,code=("MODULE",module_id,module_title,module_code) if module_id else ("SUBJECT",subject_id,subject_name,subject_code)
        g=groups.setdefault((scope_type,scope_id),{"subject_id":scope_id,"subject_name":name,"subject_code":code,"scope_type":scope_type,"scope_id":scope_id,"present":0,"absent":0,"total":0,"class_types":set()});g["total"]+=1
        if class_type_name or legacy_class_type:g["class_types"].add(class_type_name or legacy_class_type)
        if status in PASSING:g["present"]+=1
        else:g["absent"]+=1
    for g in groups.values():
        g["percentage"]=round(100*g["present"]/g["total"],2) if g["total"] else 0
        g["class_types"]=sorted(g["class_types"])
    return list(groups.values())


def attendance_alert_body(student: Student, stat: dict) -> str:
    name = student.user.name if student.user else student.name or student.roll_number
    module = stat["subject_name"] or "your scheduled module"
    if stat.get("subject_code"):
        module = f"{module} ({stat['subject_code']})"
    class_types = ", ".join(stat.get("class_types") or []) or "Scheduled class"
    return (
        f"Hello {name},\n\n"
        f"Your attendance in {module} has dropped below {settings.attendance_threshold_percent}%.\n"
        f"Current attendance: {stat['percentage']:.2f}%\n"
        f"Class type: {class_types}\n\n"
        "Please attend upcoming classes and contact your teacher or college administrator if you need support."
    )
def run_risk_evaluations(db:Session)->dict:
    evaluated=triggered=created=updated=0
    students=db.scalars(select(Student)).all()
    for student in students:
        for stat in subject_stats(db,student.id):
            evaluated+=1
            if stat["total"]>=settings.minimum_observations and stat["percentage"]<settings.attendance_threshold_percent:
                triggered+=1;case,was_created=get_or_create_attendance_case(db,student.id,stat["scope_type"],stat["scope_id"],stat["percentage"]);created+=was_created;updated+=not was_created
                if was_created:
                    queue_notification(db,"student",student.id,"Attendance alert: action needed",attendance_alert_body(student,stat),"case",case.id)
                    for guardian in db.scalars(select(Guardian).where(Guardian.student_id==student.id)).all():queue_notification(db,"guardian",guardian.id,"Attendance support alert",f"Your ward's attendance in {stat['subject_name']} has dropped below {settings.attendance_threshold_percent}%. Our team will be in touch.","case",case.id)
    db.commit();return {"evaluated":evaluated,"triggered":triggered,"created":created,"updated":updated}
