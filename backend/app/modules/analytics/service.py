from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.academic.models import Student,StudentSubjectEnrollment,Subject
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.crm.service import get_or_create_attendance_case
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry
from app.modules.academic.models import Guardian
from app.modules.operations.service import queue_notification
PASSING=(AttendanceStatus.PRESENT,AttendanceStatus.LATE)
def subject_stats(db:Session,student_id:int)->list[dict]:
    rows=db.execute(select(AttendanceRecord.status,Subject.id,Subject.name).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).join(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).join(Subject,TimetableEntry.subject_id==Subject.id).where(AttendanceRecord.student_id==student_id,ClassSession.status==SessionStatus.COMPLETED)).all();groups={}
    for status,sid,name in rows:
        g=groups.setdefault(sid,{"subject_id":sid,"subject_name":name,"present":0,"total":0});g["total"]+=1;g["present"]+=status in PASSING
    for g in groups.values():g["percentage"]=round(100*g["present"]/g["total"],2) if g["total"] else 0
    return list(groups.values())
def run_risk_evaluations(db:Session)->dict:
    evaluated=triggered=created=updated=0
    students=db.scalars(select(Student)).all()
    for student in students:
        for stat in subject_stats(db,student.id):
            evaluated+=1
            if stat["total"]>=settings.minimum_observations and stat["percentage"]<settings.attendance_threshold_percent:
                triggered+=1;case,was_created=get_or_create_attendance_case(db,student.id,stat["subject_id"],stat["percentage"]);created+=was_created;updated+=not was_created
                if was_created:
                    for guardian in db.scalars(select(Guardian).where(Guardian.student_id==student.id)).all():queue_notification(db,"guardian",guardian.id,"Attendance support alert",f"Your ward's attendance in {stat['subject_name']} has dropped below {settings.attendance_threshold_percent}%. Our team will be in touch.","case",case.id)
    db.commit();return {"evaluated":evaluated,"triggered":triggered,"created":created,"updated":updated}
