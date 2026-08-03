from datetime import date,datetime,time
from pydantic import BaseModel,ConfigDict
class ORM(BaseModel):model_config=ConfigDict(from_attributes=True)
class TimetableCreate(BaseModel):teacher_id:int;subject_id:int;section_id:int;day_of_week:int;start_time:time;end_time:time;room_name:str;latitude:float;longitude:float
class TimetableRead(TimetableCreate,ORM):id:int
class OverrideCreate(BaseModel):timetable_entry_id:int;override_date:date;new_teacher_id:int|None=None;new_room:str|None=None;start_time:time|None=None;end_time:time|None=None;is_cancelled:bool=False;reason:str
class OverrideDecision(BaseModel):status:str
class OverrideRead(OverrideCreate,ORM):id:int;status:str;created_by:int
class CurrentSession(BaseModel):timetable_entry_id:int;subject_name:str;original_teacher_id:int;effective_teacher_id:int;original_room:str;room_name:str;start_time:time;end_time:time;class_session_id:int|None=None;status:str|None=None;override_id:int|None=None
class ClassSessionRead(ORM):id:int;timetable_entry_id:int;session_date:date;effective_teacher_id:int;effective_room:str;status:str;started_at:datetime
class SessionHistory(BaseModel):id:int;session_date:date;subject_name:str;effective_teacher_id:int;effective_room:str;status:str;finalized_at:datetime|None
