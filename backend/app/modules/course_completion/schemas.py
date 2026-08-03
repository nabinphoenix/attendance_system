from datetime import date,time
from pydantic import BaseModel,ConfigDict
class PlanCreate(BaseModel):subject_id:int;batch_id:int;planned_sessions:int
class PlanRead(BaseModel):model_config=ConfigDict(from_attributes=True);id:int;subject_id:int;batch_id:int;planned_sessions:int;conducted_sessions:int;deficit:int
class SuggestionRead(BaseModel):model_config=ConfigDict(from_attributes=True);id:int;course_plan_id:int;suggested_date:date;suggested_start_time:time;suggested_room:str;teacher_id:int;status:str
class SuggestionDecision(BaseModel):status:str
