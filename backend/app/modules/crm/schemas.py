from datetime import datetime
from pydantic import BaseModel,ConfigDict
class InteractionCreate(BaseModel):channel:str;notes:str;outcome:str|None=None
class InteractionRead(InteractionCreate):model_config=ConfigDict(from_attributes=True);id:int;staff_id:int;logged_at:datetime
class CaseRead(BaseModel):model_config=ConfigDict(from_attributes=True);id:int;student_id:int;trigger_type:str;scope_type:str;scope_id:int;status:str;priority:str;assigned_to:int|None;opened_at:datetime;closed_at:datetime|None;last_evaluated_at:datetime
class CaseDetail(CaseRead):interactions:list[InteractionRead]
class Assignment(BaseModel):assigned_to:int
class StatusChange(BaseModel):status:str;note:str|None=None
