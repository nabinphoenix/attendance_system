from typing import Annotated, TypeVar
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.dependencies import DbSession, require_role
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from app.modules.operations.service import log_audit
from . import schemas
from .models import Batch, Guardian, Intake, Program, Section, Student, StudentSubjectEnrollment, Subject, Teacher
from .module_offering_service import synchronize_section_module_offerings
from app.modules.scheduling.models import ClassSession, ScheduleOverride, TimetableEntry

router = APIRouter(prefix="/academic", tags=["academic"], dependencies=[Depends(require_role("admin"))])
T = TypeVar("T")
def save(db: Session, obj: T) -> T:
    db.add(obj); db.commit(); db.refresh(obj); return obj
def save_with_audit(db: Session, obj: T, actor_id: int, action: str, entity_type: str, after: dict) -> T:
    db.add(obj); db.flush(); log_audit(db, actor_id, action, entity_type, obj.id, None, after); db.commit(); db.refresh(obj); return obj
def create_user(db: Session, name: str, email: str, password: str, role: UserRole) -> User:
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user); db.flush(); return user

def get_or_404(db: Session, model: type[T], id: int, label: str) -> T:
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(404, f"{label} not found")
    return obj

def update(db: Session, obj: T, values: dict) -> T:
    for key, value in values.items():
        setattr(obj, key, value)
    return save(db, obj)

def teacher_read(teacher: Teacher) -> schemas.TeacherRead:
    return schemas.TeacherRead(id=teacher.id, user_id=teacher.user_id, employee_code=teacher.employee_code, name=teacher.user.name, email=teacher.user.email)

def page(db: Session, query, response_type, page_number: int, page_size: int):
    page_number=max(page_number,1); page_size=min(max(page_size,1),100)
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items=db.scalars(query.offset((page_number-1)*page_size).limit(page_size)).all()
    return response_type(items=items,total=total,page=page_number,page_size=page_size)

def delete_with_audit(db: Session, obj: T, actor_id: int, action: str, entity_type: str) -> None:
    entity_id=obj.id; db.delete(obj); log_audit(db,actor_id,action,entity_type,entity_id,{"id":entity_id},None); db.commit()

@router.post("/programs", response_model=schemas.ProgramRead)
def create_program(p: schemas.ProgramCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession): return save_with_audit(db, Program(**p.model_dump()), user.id, "program.created", "program", p.model_dump())
@router.get("/programs", response_model=list[schemas.ProgramRead])
def programs(db: DbSession): return db.scalars(select(Program).order_by(Program.name)).all()
@router.get("/programs/page", response_model=schemas.ProgramPage)
def program_page(db: DbSession,page_number:int=1,page_size:int=20): return page(db,select(Program).order_by(Program.name),schemas.ProgramPage,page_number,page_size)
@router.patch("/programs/{id}", response_model=schemas.ProgramRead)
def update_program(id: int, p: schemas.ProgramUpdate, db: DbSession): return update(db, get_or_404(db, Program, id, "Program"), p.model_dump(exclude_none=True))
@router.delete("/programs/{id}", status_code=204)
def delete_program(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Program,id,"Program")
    if db.scalar(select(Batch.id).where(Batch.program_id==id)):raise HTTPException(409,"Cannot delete a program with batches")
    delete_with_audit(db,obj,user.id,"program.deleted","program")

@router.post("/batches", response_model=schemas.BatchRead)
def create_batch(p: schemas.BatchCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    get_or_404(db, Program, p.program_id, "Program")
    return save_with_audit(db, Batch(**p.model_dump()), user.id, "batch.created", "batch", p.model_dump())
@router.get("/batches", response_model=list[schemas.BatchRead])
def batches(db: DbSession): return db.scalars(select(Batch).order_by(Batch.name)).all()
@router.get("/batches/page", response_model=schemas.BatchPage)
def batch_page(db:DbSession,page_number:int=1,page_size:int=20):return page(db,select(Batch).order_by(Batch.name),schemas.BatchPage,page_number,page_size)
@router.patch("/batches/{id}", response_model=schemas.BatchRead)
def update_batch(id: int, p: schemas.BatchUpdate, db: DbSession):
    if p.program_id is not None: get_or_404(db, Program, p.program_id, "Program")
    return update(db, get_or_404(db, Batch, id, "Batch"), p.model_dump(exclude_none=True))
@router.delete("/batches/{id}", status_code=204)
def delete_batch(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Batch,id,"Batch")
    if db.scalar(select(Section.id).where(Section.batch_id==id)):raise HTTPException(409,"Cannot delete a batch with sections")
    delete_with_audit(db,obj,user.id,"batch.deleted","batch")

@router.post("/sections", response_model=schemas.SectionRead)
def create_section(p: schemas.SectionCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    get_or_404(db, Batch, p.batch_id, "Batch")
    if p.intake_id is not None: get_or_404(db, Intake, p.intake_id, "Intake")
    section = Section(**p.model_dump())
    db.add(section)
    db.flush()
    inherited = synchronize_section_module_offerings(db, section)
    after = p.model_dump() | {"inherited_module_offering_ids": [offering.id for offering in inherited]}
    log_audit(db, user.id, "section.created", "section", section.id, None, after)
    db.commit()
    db.refresh(section)
    return section
@router.get("/sections", response_model=list[schemas.SectionRead])
def sections(db: DbSession): return db.scalars(select(Section).order_by(Section.name)).all()
@router.get("/sections/page", response_model=schemas.SectionPage)
def section_page(db:DbSession,page_number:int=1,page_size:int=20):return page(db,select(Section).order_by(Section.name),schemas.SectionPage,page_number,page_size)
@router.patch("/sections/{id}", response_model=schemas.SectionRead)
def update_section(id: int, p: schemas.SectionUpdate, db: DbSession):
    if p.batch_id is not None: get_or_404(db, Batch, p.batch_id, "Batch")
    if p.intake_id is not None: get_or_404(db, Intake, p.intake_id, "Intake")
    section = get_or_404(db, Section, id, "Section")
    values = p.model_dump(exclude_none=True)
    for key, value in values.items():
        setattr(section, key, value)
    db.flush()
    synchronize_section_module_offerings(db, section)
    return save(db, section)
@router.delete("/sections/{id}", status_code=204)
def delete_section(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Section,id,"Section")
    from .models import RoutineEntrySection
    if db.scalar(select(Student.id).where(Student.section_id==id)) or db.scalar(select(Subject.id).where(Subject.section_id==id)) or db.scalar(select(RoutineEntrySection.id).where(RoutineEntrySection.section_id==id)):raise HTTPException(409,"Cannot delete a section with students, subjects, or routine entries")
    delete_with_audit(db,obj,user.id,"section.deleted","section")

@router.post("/subjects", response_model=schemas.SubjectRead)
def create_subject(p: schemas.SubjectCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    get_or_404(db, Section, p.section_id, "Section")
    return save_with_audit(db, Subject(**p.model_dump()), user.id, "subject.created", "subject", p.model_dump())
@router.get("/subjects", response_model=list[schemas.SubjectRead])
def subjects(db: DbSession): return db.scalars(select(Subject).order_by(Subject.code)).all()
@router.get("/subjects/page", response_model=schemas.SubjectPage)
def subject_page(db:DbSession,page_number:int=1,page_size:int=20):return page(db,select(Subject).order_by(Subject.code),schemas.SubjectPage,page_number,page_size)
@router.patch("/subjects/{id}", response_model=schemas.SubjectRead)
def update_subject(id: int, p: schemas.SubjectUpdate, db: DbSession):
    if p.section_id is not None: get_or_404(db, Section, p.section_id, "Section")
    return update(db, get_or_404(db, Subject, id, "Subject"), p.model_dump(exclude_none=True))
@router.delete("/subjects/{id}", status_code=204)
def delete_subject(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Subject,id,"Subject")
    if db.scalar(select(TimetableEntry.id).where(TimetableEntry.subject_id==id)) or db.scalar(select(StudentSubjectEnrollment.id).where(StudentSubjectEnrollment.subject_id==id)):raise HTTPException(409,"Cannot delete a subject with timetable entries or enrollments")
    delete_with_audit(db,obj,user.id,"subject.deleted","subject")
@router.post("/guardians", response_model=schemas.GuardianRead)
def create_guardian(p: schemas.GuardianCreate, db: DbSession): return save(db, Guardian(**p.model_dump()))
@router.post("/students", response_model=schemas.StudentRead)
def create_student(p: schemas.StudentCreate, db: DbSession):
    user = create_user(db, p.name, p.email, p.password, UserRole.STUDENT)
    subjects = [db.get(Subject, i) for i in p.subject_ids]
    if any(x is None for x in subjects): raise HTTPException(404, "Subject not found")
    return save(db, Student(user_id=user.id, section_id=p.section_id, roll_number=p.roll_number, name=p.name, email=str(p.email), subjects=subjects))
@router.post("/teachers", response_model=schemas.TeacherRead)
def create_teacher(p: schemas.TeacherCreate, actor: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    user = create_user(db, p.name, p.email, p.password, UserRole.TEACHER)
    teacher=save_with_audit(db, Teacher(user_id=user.id, employee_code=p.employee_code), actor.id, "teacher.created", "teacher", {"user_id":user.id,"email":user.email,"employee_code":p.employee_code})
    return teacher_read(teacher)
@router.get("/students/{id}", response_model=schemas.StudentRead)
def get_student(id: int, db: DbSession):
    if not (obj := db.get(Student, id)): raise HTTPException(404, "Student not found")
    return obj
@router.get("/teachers/page",response_model=schemas.TeacherPage)
def teacher_page(db:DbSession,page_number:int=1,page_size:int=20):
    page_number=max(page_number,1);page_size=min(max(page_size,1),100);q=select(Teacher).order_by(Teacher.employee_code);total=db.scalar(select(func.count()).select_from(q.subquery())) or 0;items=[teacher_read(teacher) for teacher in db.scalars(q.offset((page_number-1)*page_size).limit(page_size)).all()];return schemas.TeacherPage(items=items,total=total,page=page_number,page_size=page_size)
@router.get("/teachers/{id}", response_model=schemas.TeacherRead)
def get_teacher(id: int, db: DbSession):
    return teacher_read(get_or_404(db, Teacher, id, "Teacher"))
@router.get("/teachers",response_model=list[schemas.TeacherRead])
def teachers(db:DbSession): return [teacher_read(teacher) for teacher in db.scalars(select(Teacher).order_by(Teacher.employee_code)).all()]
@router.patch("/teachers/{id}", response_model=schemas.TeacherRead)
def update_teacher(id: int, p: schemas.TeacherUpdate, db: DbSession):
    teacher = get_or_404(db, Teacher, id, "Teacher")
    values = p.model_dump(exclude_none=True)
    if "name" in values: teacher.user.name = values["name"]
    if "email" in values:
        existing = db.scalar(select(User).where(User.email == str(values["email"]), User.id != teacher.user_id))
        if existing: raise HTTPException(409, "An account with this email already exists")
        teacher.user.email = str(values["email"])
    if "password" in values: teacher.user.password_hash = hash_password(values["password"])
    if "employee_code" in values: teacher.employee_code = values["employee_code"]
    return teacher_read(save(db, teacher))
@router.delete("/teachers/{id}",status_code=204)
def delete_teacher(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    teacher=get_or_404(db,Teacher,id,"Teacher")
    from .models import RoutineEntry
    if db.scalar(select(TimetableEntry.id).where(TimetableEntry.teacher_id==id)) or db.scalar(select(RoutineEntry.id).where(RoutineEntry.teacher_id==id)) or db.scalar(select(ScheduleOverride.id).where(ScheduleOverride.new_teacher_id==id)) or db.scalar(select(ClassSession.id).where(ClassSession.effective_teacher_id==id)):raise HTTPException(409,"Cannot delete a teacher with timetable, routine, override, or session history")
    account=teacher.user;entity_id=teacher.id;db.delete(teacher);db.flush();db.delete(account);log_audit(db,user.id,"teacher.deleted","teacher",entity_id,{"user_id":account.id},None);db.commit()
@router.post("/students/{id}/enrollments", response_model=schemas.SubjectRead)
def enroll(id:int,p:schemas.EnrollmentCreate,db:DbSession):
    student=db.get(Student,id);subject=db.get(Subject,p.subject_id)
    if not student or not subject:raise HTTPException(404,"Student or subject not found")
    if subject not in student.subjects:student.subjects.append(subject);db.commit()
    return subject
@router.get("/students/{id}/subjects",response_model=list[schemas.SubjectRead])
def student_subjects(id:int,db:DbSession):
    student=db.get(Student,id)
    if not student:raise HTTPException(404,"Student not found")
    return student.subjects
@router.get("/sections/{id}/students",response_model=list[schemas.StudentRead])
def section_students(id:int,db:DbSession):return db.scalars(select(Student).where(Student.section_id==id)).all()
