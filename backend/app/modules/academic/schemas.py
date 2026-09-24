from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class ORMModel(BaseModel): model_config = ConfigDict(from_attributes=True)
class ProgramCreate(BaseModel): name: str
class ProgramRead(ORMModel): id: int; name: str
class ProgramUpdate(BaseModel): name: str | None = None
class ProgramPage(BaseModel): items: list[ProgramRead]; total: int; page: int; page_size: int
class SemesterDetails(BaseModel):
    """Administrator-entered details for one of a Level's two semesters.

    Semester numbers are not accepted here: the server derives those immutable
    numbers from the selected Level.
    """
    display_name: str = Field(min_length=1, max_length=150)
    start_date: date
    end_date: date
class BatchLevelSeed(BaseModel):
    level_number: int = Field(ge=1, le=3)
    intake_code: str = Field(min_length=1, max_length=50)
    intake_name: str | None = Field(default=None, max_length=100)
class BatchLevelCreate(BatchLevelSeed):
    batch_id: int
    semesters: list[SemesterDetails] = Field(min_length=2, max_length=2)
class BatchLevelUpdate(BaseModel):
    intake_code: str | None = Field(default=None, min_length=1, max_length=50)
    intake_name: str | None = Field(default=None, max_length=100)
class BatchLevelRead(ORMModel):
    id: int
    batch_id: int
    level_number: int
    intake_id: int
    intake_code: str
    intake_name: str | None = None
class BatchCreate(BaseModel):
    name: str
    program_id: int
    start_date: date
    end_date: date
    # New batches are created before their yearly Intake Codes. Keep this
    # optional for existing API callers that still create a batch and levels
    # in one request.
    levels: list[BatchLevelSeed] = Field(default_factory=list)
class BatchRead(ORMModel):
    id: int
    name: str
    program_id: int
    start_date: date
    end_date: date
    levels: list[BatchLevelRead] = Field(default_factory=list)
class BatchUpdate(BaseModel):
    name: str | None = None
    program_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
class BatchPage(BaseModel): items: list[BatchRead]; total: int; page: int; page_size: int
class SectionCreate(BaseModel): name: str; batch_id: int; combined_with: str | None = None
class SectionRead(ORMModel): id: int; name: str; batch_id: int; combined_with: str | None = None
class SectionUpdate(BaseModel): name: str | None = None; batch_id: int | None = None; combined_with: str | None = None
class SectionPage(BaseModel): items: list[SectionRead]; total: int; page: int; page_size: int
class SubjectCreate(BaseModel): name: str; code: str; section_id: int
class SubjectRead(ORMModel): id: int; name: str; code: str; section_id: int
class SubjectUpdate(BaseModel): name: str | None = None; code: str | None = None; section_id: int | None = None
class SubjectPage(BaseModel): items: list[SubjectRead]; total: int; page: int; page_size: int
class EnrollmentCreate(BaseModel): subject_id: int
class PersonCreate(BaseModel): name: str; email: EmailStr; password: str
class StudentCreate(PersonCreate): section_id: int; roll_number: str; subject_ids: list[int] = []
class StudentRead(ORMModel):
    id: int
    user_id: int | None
    section_id: int
    roll_number: str
    name: str | None = None
    email: str | None = None
class TeacherCreate(PersonCreate): employee_code: str
class TeacherUpdate(BaseModel): name: str | None = None; email: EmailStr | None = None; password: str | None = None; employee_code: str | None = None
class TeacherRead(ORMModel): id: int; user_id: int; employee_code: str; name: str; email: EmailStr
class TeacherPage(BaseModel): items: list[TeacherRead]; total: int; page: int; page_size: int
class GuardianCreate(BaseModel): name: str; student_id: int
class GuardianRead(ORMModel): id: int; name: str; student_id: int
