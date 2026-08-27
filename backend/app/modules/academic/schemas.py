from pydantic import BaseModel, ConfigDict, EmailStr

class ORMModel(BaseModel): model_config = ConfigDict(from_attributes=True)
class ProgramCreate(BaseModel): name: str
class ProgramRead(ORMModel): id: int; name: str
class ProgramUpdate(BaseModel): name: str | None = None
class ProgramPage(BaseModel): items: list[ProgramRead]; total: int; page: int; page_size: int
class BatchCreate(BaseModel): name: str; program_id: int
class BatchRead(ORMModel): id: int; name: str; program_id: int
class BatchUpdate(BaseModel): name: str | None = None; program_id: int | None = None
class BatchPage(BaseModel): items: list[BatchRead]; total: int; page: int; page_size: int
class SectionCreate(BaseModel): name: str; batch_id: int; intake_id: int | None = None; semester_number: int | None = None; combined_with: str | None = None
class SectionRead(ORMModel): id: int; name: str; batch_id: int; intake_id: int | None = None; semester_number: int | None = None; combined_with: str | None = None
class SectionUpdate(BaseModel): name: str | None = None; batch_id: int | None = None; intake_id: int | None = None; semester_number: int | None = None; combined_with: str | None = None
class SectionPage(BaseModel): items: list[SectionRead]; total: int; page: int; page_size: int
class SubjectCreate(BaseModel): name: str; code: str; section_id: int
class SubjectRead(ORMModel): id: int; name: str; code: str; section_id: int
class SubjectUpdate(BaseModel): name: str | None = None; code: str | None = None; section_id: int | None = None
class SubjectPage(BaseModel): items: list[SubjectRead]; total: int; page: int; page_size: int
class EnrollmentCreate(BaseModel): subject_id: int
class PersonCreate(BaseModel): name: str; email: EmailStr; password: str
class StudentCreate(PersonCreate): section_id: int; roll_number: str; subject_ids: list[int] = []
class StudentRead(ORMModel): id: int; user_id: int | None; section_id: int; roll_number: str
class TeacherCreate(PersonCreate): employee_code: str
class TeacherUpdate(BaseModel): name: str | None = None; email: EmailStr | None = None; password: str | None = None; employee_code: str | None = None
class TeacherRead(ORMModel): id: int; user_id: int; employee_code: str; name: str; email: EmailStr
class TeacherPage(BaseModel): items: list[TeacherRead]; total: int; page: int; page_size: int
class GuardianCreate(BaseModel): name: str; student_id: int
class GuardianRead(ORMModel): id: int; name: str; student_id: int
