from datetime import date,datetime,time
from pydantic import BaseModel,ConfigDict,Field
class ORM(BaseModel):model_config=ConfigDict(from_attributes=True)
class TimetableCreate(BaseModel):teacher_id:int;subject_id:int;section_id:int;class_type:str="lecture";day_of_week:int;start_time:time;end_time:time;room_name:str;latitude:float=0;longitude:float=0
class TimetableRead(TimetableCreate,ORM):id:int
class OverrideCreate(BaseModel):timetable_entry_id:int;override_date:date;new_teacher_id:int|None=None;new_room:str|None=None;start_time:time|None=None;end_time:time|None=None;is_cancelled:bool=False;reason:str
class OverrideDecision(BaseModel):status:str
class OverrideRead(OverrideCreate,ORM):id:int;status:str;created_by:int
class CurrentSession(BaseModel):timetable_entry_id:int;subject_name:str;original_teacher_id:int;effective_teacher_id:int;original_room:str;room_name:str;start_time:time;end_time:time;class_session_id:int|None=None;status:str|None=None;override_id:int|None=None
class SessionGeofenceCapture(BaseModel):
 model_config=ConfigDict(extra="forbid")
 latitude:float=Field(ge=-90,le=90);longitude:float=Field(ge=-180,le=180);accuracy_meters:float=Field(ge=0);geofence_radius_meters:float|None=Field(default=None,gt=0)
class ClassSessionRead(ORM):
 id:int;timetable_entry_id:int|None=None;routine_entry_id:int|None=None;session_date:date;effective_teacher_id:int;effective_room:str;status:str;started_at:datetime
 geofence_radius_meters:float|None=None;teacher_location_accuracy_meters:float|None=None;geofence_captured_at:datetime|None=None
class SessionHistory(BaseModel):id:int;session_date:date;subject_name:str;effective_teacher_id:int;effective_room:str;status:str;finalized_at:datetime|None
