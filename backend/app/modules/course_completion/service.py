from datetime import date,datetime,time,timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.academic.models import Section,Subject
from app.modules.course_completion.models import CoursePlan
from app.modules.scheduling.models import ClassSession,ScheduleOverride,TimetableEntry
def overlaps(start:time,end:time,other_start:time,other_end:time)->bool:return start<other_end and end>other_start
def find_makeup_slot(db:Session,course_plan_id:int)->dict|None:
    plan=db.get(CoursePlan,course_plan_id)
    if not plan:return None
    entry=db.scalar(select(TimetableEntry).join(Section,TimetableEntry.section_id==Section.id).where(TimetableEntry.subject_id==plan.subject_id,Section.batch_id==plan.batch_id))
    if not entry:return None
    all_entries=db.scalars(select(TimetableEntry)).all();today=date.today();end_date=today+timedelta(days=14);sessions=db.scalars(select(ClassSession).where(ClassSession.session_date.between(today,end_date))).all();rooms=sorted({x.room_name for x in all_entries}|{x.effective_room for x in sessions}) or [entry.room_name]
    for offset in range(15):
        candidate_date=today+timedelta(days=offset)
        if candidate_date.weekday()>=5:continue
        if db.scalar(select(ScheduleOverride.id).where(ScheduleOverride.timetable_entry_id==entry.id,ScheduleOverride.override_date==candidate_date)):continue
        for hour in range(8,16):
            start=time(hour);end=time(hour+1)
            teacher_busy=any(x.day_of_week==candidate_date.weekday() and x.teacher_id==entry.teacher_id and overlaps(start,end,x.start_time,x.end_time) for x in all_entries)
            batch_busy=any(x.day_of_week==candidate_date.weekday() and x.section.batch_id==plan.batch_id and overlaps(start,end,x.start_time,x.end_time) for x in all_entries)
            teacher_busy=teacher_busy or any(x.session_date==candidate_date and x.effective_teacher_id==entry.teacher_id and overlaps(start,end,x.timetable_entry.start_time,x.timetable_entry.end_time) for x in sessions)
            batch_busy=batch_busy or any(x.session_date==candidate_date and x.timetable_entry.section.batch_id==plan.batch_id and overlaps(start,end,x.timetable_entry.start_time,x.timetable_entry.end_time) for x in sessions)
            if teacher_busy or batch_busy:continue
            for room in rooms:
                room_busy=any(x.day_of_week==candidate_date.weekday() and x.room_name==room and overlaps(start,end,x.start_time,x.end_time) for x in all_entries)
                room_busy=room_busy or any(x.session_date==candidate_date and x.effective_room==room and overlaps(start,end,x.timetable_entry.start_time,x.timetable_entry.end_time) for x in sessions)
                if not room_busy:return {"date":candidate_date,"start_time":start,"room":room,"teacher_id":entry.teacher_id,"timetable_entry_id":entry.id}
    return None
