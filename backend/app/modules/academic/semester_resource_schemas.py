from datetime import date, datetime
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeedbackWrite(BaseModel):
    title: str = Field(default="Mid-semester teacher feedback", min_length=1, max_length=200)
    form_url: str = Field(max_length=2048)
    opens_on: date
    closes_on: date
    is_published: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a feedback title")
        return value

    @field_validator("form_url")
    @classmethod
    def google_form_link(cls, value: str) -> str:
        value = value.strip()
        url = urlsplit(value)
        safe_origin = (
            url.scheme == "https" and not url.username and not url.password
            and url.port in (None, 443) and not any(c.isspace() for c in value)
            and "\\" not in value
        )
        responder_path = re.fullmatch(r"/forms/(?:u/\d+/)?d/(?:e/)?[A-Za-z0-9_-]+/viewform/?", url.path)
        short_path = re.fullmatch(r"/[A-Za-z0-9_-]+/?", url.path)
        if not safe_origin or not (
            (url.hostname == "docs.google.com" and responder_path)
            or (url.hostname == "forms.gle" and short_path)
        ):
            raise ValueError("Use a Google Forms responder link (docs.google.com/forms/.../viewform or forms.gle/...)")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.opens_on > self.closes_on:
            raise ValueError("Feedback opening date must be on or before its closing date")
        return self


class FeedbackRead(BaseModel):
    id: int
    cohort_semester_id: int
    teacher_id: int
    teacher_name: str
    title: str
    form_url: str | None
    opens_on: date
    closes_on: date
    is_published: bool
    status: Literal["draft", "scheduled", "open", "closed"]


class CalendarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cohort_semester_id: int
    filename: str
    size_bytes: int
    uploaded_at: datetime


class SemesterResourcesRead(BaseModel):
    id: int
    intake_name: str
    batch_name: str
    semester_number: int
    attempt_number: int
    start_date: date
    end_date: date
    calendar: CalendarRead | None


class FeedbackTeacherRead(BaseModel):
    id: int
    name: str
    employee_code: str
