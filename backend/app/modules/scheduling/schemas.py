from datetime import date, datetime, time
from pydantic import BaseModel, ConfigDict
class TimetableCreate(BaseModel):
    teacher_id: int; subject_id: int; section_id: int; day_of_week: int; start_time: time; end_time: time; room_name: str; latitude: float; longitude: float
class TimetableRead(TimetableCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
class CurrentSession(BaseModel):
    timetable_entry_id: int; subject_name: str; room_name: str; start_time: time; end_time: time; class_session_id: int | None = None; status: str | None = None
class ClassSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; timetable_entry_id: int; session_date: date; status: str; started_at: datetime
