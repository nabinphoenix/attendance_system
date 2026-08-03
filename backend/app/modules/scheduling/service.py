from datetime import date,time
from sqlalchemy.orm import Session
from app.modules.scheduling.models import OverrideStatus,ScheduleOverride
def create_schedule_override(db:Session,*,timetable_entry_id:int,override_date:date,created_by:int,reason:str,new_teacher_id:int|None=None,new_room:str|None=None,start_time:time|None=None,end_time:time|None=None,is_cancelled:bool=False,status:OverrideStatus=OverrideStatus.PENDING)->ScheduleOverride:
    obj=ScheduleOverride(timetable_entry_id=timetable_entry_id,override_date=override_date,created_by=created_by,reason=reason,new_teacher_id=new_teacher_id,new_room=new_room,start_time=start_time,end_time=end_time,is_cancelled=is_cancelled,status=status);db.add(obj);db.flush();return obj
