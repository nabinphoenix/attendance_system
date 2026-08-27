from datetime import date,time
from pydantic import BaseModel,ConfigDict,Field,model_validator


class PlanCreate(BaseModel):
    subject_id: int | None = None
    module_offering_id: int | None = None
    batch_id: int
    planned_sessions: int = Field(ge=1)

    @model_validator(mode="after")
    def require_exactly_one_source(self):
        if (self.subject_id is None) == (self.module_offering_id is None):
            raise ValueError("Provide exactly one of subject_id or module_offering_id")
        return self


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subject_id: int | None
    module_offering_id: int | None
    batch_id: int
    planned_sessions: int
    conducted_sessions: int
    deficit: int


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_plan_id: int
    suggested_date: date
    suggested_start_time: time
    suggested_room: str
    teacher_id: int
    timetable_entry_id: int | None
    routine_entry_id: int | None
    status: str
class SuggestionDecision(BaseModel):status:str
