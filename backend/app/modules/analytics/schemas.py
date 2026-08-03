from datetime import date
from pydantic import BaseModel
class SubjectAttendance(BaseModel):subject_id:int;subject_name:str;present:int;total:int;percentage:float
class StudentSummary(BaseModel):student_id:int;overall_percentage:float;subjects:list[SubjectAttendance]
class SectionStudentSummary(BaseModel):student_id:int;student_name:str;percentage:float
class SectionSummary(BaseModel):section_id:int;overall_percentage:float;students:list[SectionStudentSummary]
class SelectiveCandidate(BaseModel):student_id:int;date:date;attended_subjects:list[str];missed_subjects:list[str]
class RiskRunResult(BaseModel):evaluated:int;triggered:int;created:int;updated:int
