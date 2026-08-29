from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LocationFailure = Literal["LOCATION_DENIED", "LOCATION_TIMEOUT", "LOCATION_UNAVAILABLE"]


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qr_token: str = Field(min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0)
    location_failure_reason: LocationFailure | None = None


class CheckInResponse(BaseModel):
    status: Literal["present", "pending_verification"]
    reason: str | None = None
    check_in_time: datetime | None = None
    module_title: str
    room: str
    start_time: time
    message: str


class QRResponse(BaseModel):
    token: str
    expires_at: datetime
    rotation_seconds: int
    module_title: str
    section_names: list[str]
    room: str
    start_time: time
    end_time: time
    geofence_radius_meters: float | None
    teacher_location_accuracy_meters: float | None


class RosterItem(BaseModel):
    attendance_id: int | None
    student_id: int
    student_name: str
    roll_number: str
    status: str
    check_in_time: datetime | None = None
    distance_meters: float | None = None
    allowed_radius_meters: float | None = None
    location_accuracy_meters: float | None = None


class TeacherAttendanceClass(BaseModel):
    routine_id: int
    session_id: int | None
    date: date
    module_code: str
    module_title: str
    section_names: list[str]
    start_time: time
    end_time: time
    room: str
    cancelled: bool
    session_status: str | None
    students: list[RosterItem]


class CheckInExceptionRead(BaseModel):
    id: int
    student_name: str
    roll_number: str
    section_name: str
    reason: str
    distance_meters: float | None
    allowed_radius_meters: float | None
    accuracy_meters: float | None
    created_at: datetime
    status: str


class ExceptionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["confirm", "reject"]
    reason: str = Field(min_length=1, max_length=500)


class StatusChange(BaseModel):
    status: str
    reason: str
