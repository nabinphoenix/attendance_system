from pydantic import BaseModel, ConfigDict, EmailStr
class ORMModel(BaseModel): model_config = ConfigDict(from_attributes=True)
class ProgramCreate(BaseModel): name: str
class ProgramRead(ORMModel): id: int; name: str
class BatchCreate(BaseModel): name: str; program_id: int
class BatchRead(ORMModel): id: int; name: str; program_id: int
class SectionCreate(BaseModel): name: str; batch_id: int
class SectionRead(ORMModel): id: int; name: str; batch_id: int
class SubjectCreate(BaseModel): name: str; code: str; section_id: int
class SubjectRead(ORMModel): id: int; name: str; code: str; section_id: int
class EnrollmentCreate(BaseModel): subject_id: int
class PersonCreate(BaseModel): name: str; email: EmailStr; password: str
class StudentCreate(PersonCreate): section_id: int; roll_number: str; subject_ids: list[int] = []
class StudentRead(ORMModel): id: int; user_id: int; section_id: int; roll_number: str
class TeacherCreate(PersonCreate): employee_code: str
class TeacherRead(ORMModel): id: int; user_id: int; employee_code: str
class GuardianCreate(BaseModel): name: str; student_id: int
class GuardianRead(ORMModel): id: int; name: str; student_id: int
