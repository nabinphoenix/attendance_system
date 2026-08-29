from datetime import date, datetime
from pydantic import BaseModel
class SubjectAttendance(BaseModel):subject_id:int;subject_name:str;present:int;absent:int;total:int;percentage:float
class StudentSummary(BaseModel):student_id:int;present:int;absent:int;total:int;overall_percentage:float;subjects:list[SubjectAttendance];attendance_threshold_percent:float;minimum_observations:int
class StudentAttendanceRecord(BaseModel):
    session_id:int
    date:date
    weekday:str
    subject_id:int
    subject_name:str
    subject_code:str|None
    status:str
    check_in_time:datetime|None
class StudentAttendanceDay(BaseModel):
    date:date
    weekday:str
    present:int
    absent:int
    total:int
    percentage:float
    records:list[StudentAttendanceRecord]
class StudentAttendanceReport(BaseModel):
    student_id:int
    date_from:date|None
    date_to:date|None
    present:int
    absent:int
    total:int
    overall_percentage:float
    subjects:list[SubjectAttendance]
    days:list[StudentAttendanceDay]
    attendance_threshold_percent:float
    minimum_observations:int
class SectionStudentSummary(BaseModel):student_id:int;student_name:str;percentage:float
class SectionSummary(BaseModel):section_id:int;overall_percentage:float;students:list[SectionStudentSummary]
class SelectiveCandidate(BaseModel):student_id:int;date:date;attended_subjects:list[str];missed_subjects:list[str]
class RiskRunResult(BaseModel):evaluated:int;triggered:int;created:int;updated:int
class CollegeSummary(BaseModel):attendance_percentage:float;open_cases_by_priority:dict[str,int];pending_overrides:int;pending_makeup_suggestions:int
class AtRiskStudent(BaseModel):student_id:int;student_name:str;subject_id:int;subject_name:str;attendance_percentage:float;observations:int;case_status:str|None
