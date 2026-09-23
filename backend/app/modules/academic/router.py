from datetime import date, timedelta
from typing import Annotated, TypeVar
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app.core.dependencies import DbSession, require_role
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from app.modules.operations.service import log_audit
from . import schemas
from .models import Batch, BatchLevel, CohortSemester, Guardian, Intake, Program, Section, Student, StudentSubjectEnrollment, Subject, Teacher
from .module_offering_service import synchronize_section_module_offerings
from .models import StudentEnrollment
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

def three_year_end(start: date) -> date:
    try:
        return start.replace(year=start.year + 3) - timedelta(days=1)
    except ValueError:
        return start.replace(year=start.year + 3, day=28) - timedelta(days=1)


def validate_batch_dates(start: date, end: date) -> None:
    expected = three_year_end(start)
    if end != expected:
        raise HTTPException(
            422,
            f'A three-year batch ending after {start.isoformat()} must end on {expected.isoformat()}',
        )


def validate_level_seeds(levels: list[schemas.BatchLevelSeed]) -> None:
    if sorted(level.level_number for level in levels) != [1, 2, 3]:
        raise HTTPException(422, 'A batch requires exactly Level 1, Level 2, and Level 3')
    codes = [level.intake_code.strip().casefold() for level in levels]
    if len(set(codes)) != 3:
        raise HTTPException(422, 'Each level requires a different Intake Code')


def resolve_intake(
    db: Session,
    *,
    program_id: int,
    code: str,
    name: str | None,
) -> Intake:
    normalized = code.strip()
    intake = db.scalar(select(Intake).where(func.lower(Intake.code) == normalized.casefold()))
    if intake is not None:
        if intake.program_id != program_id:
            raise HTTPException(422, f'Intake Code {normalized} belongs to another program')
        if name is not None:
            intake.name = name.strip() or None
        return intake
    intake = Intake(code=normalized, name=(name or '').strip() or None, start_date=None, program_id=program_id)
    db.add(intake)
    db.flush()
    return intake


def section_context_values(db: Session, values: dict) -> dict:
    """Legacy helper retained for old callers during the rolling migration."""
    cohort_semester_id = values.get('cohort_semester_id')
    if cohort_semester_id is None:
        return values
    period = get_or_404(db, CohortSemester, cohort_semester_id, 'Cohort semester')
    for field, expected in (
        ('batch_id', period.batch_id),
        ('intake_id', period.intake_id),
        ('semester_number', period.semester_number),
    ):
        supplied = values.get(field)
        if supplied is not None and supplied != expected:
            raise HTTPException(422, f'{field} does not match the selected cohort semester')
        values[field] = expected
    return values

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
    validate_batch_dates(p.start_date, p.end_date)
    validate_level_seeds(p.levels)
    batch = Batch(**p.model_dump(exclude={'levels'}))
    db.add(batch)
    db.flush()
    for seed in sorted(p.levels, key=lambda item: item.level_number):
        intake = resolve_intake(
            db,
            program_id=p.program_id,
            code=seed.intake_code,
            name=seed.intake_name,
        )
        db.add(BatchLevel(batch_id=batch.id, level_number=seed.level_number, intake_id=intake.id))
    db.flush()
    log_audit(
        db,
        user.id,
        'batch.created',
        'batch',
        batch.id,
        None,
        p.model_dump(mode='json'),
    )
    db.commit()
    return db.scalar(
        select(Batch)
        .options(selectinload(Batch.levels).selectinload(BatchLevel.intake))
        .where(Batch.id == batch.id)
    )
@router.get("/batches", response_model=list[schemas.BatchRead])
def batches(db: DbSession):
    return db.scalars(
        select(Batch)
        .options(selectinload(Batch.levels).selectinload(BatchLevel.intake))
        .order_by(Batch.name)
    ).all()
@router.get("/batches/page", response_model=schemas.BatchPage)
def batch_page(db:DbSession,page_number:int=1,page_size:int=20):
    return page(
        db,
        select(Batch).options(selectinload(Batch.levels).selectinload(BatchLevel.intake)).order_by(Batch.name),
        schemas.BatchPage,
        page_number,
        page_size,
    )
@router.patch("/batches/{id}", response_model=schemas.BatchRead)
def update_batch(id: int, p: schemas.BatchUpdate, db: DbSession):
    if p.program_id is not None: get_or_404(db, Program, p.program_id, "Program")
    batch = get_or_404(db, Batch, id, "Batch")
    values = p.model_dump(exclude_none=True)
    if values.get('program_id') not in (None, batch.program_id) and batch.levels:
        raise HTTPException(409, 'Cannot change the Program after Batch Levels exist')
    if values.get('program_id') not in (None, batch.program_id) and batch.levels:
        raise HTTPException(409, 'Cannot change the Program after Batch Levels exist')
    start = values.get('start_date', batch.start_date)
    end = values.get('end_date', batch.end_date)
    validate_batch_dates(start, end)
    update(db, batch, values)
    return db.scalar(
        select(Batch)
        .options(selectinload(Batch.levels).selectinload(BatchLevel.intake))
        .where(Batch.id == id)
    )
@router.delete("/batches/{id}", status_code=204)
def delete_batch(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Batch,id,"Batch")
    if db.scalar(select(Section.id).where(Section.batch_id==id)) or db.scalar(select(CohortSemester.id).where(CohortSemester.batch_id==id)):raise HTTPException(409,"Cannot delete a batch with sections or semesters")
    delete_with_audit(db,obj,user.id,"batch.deleted","batch")

@router.get('/levels', response_model=list[schemas.BatchLevelRead])
def levels(db: DbSession, batch_id: int | None = None):
    query = select(BatchLevel).options(selectinload(BatchLevel.intake)).order_by(
        BatchLevel.batch_id, BatchLevel.level_number
    )
    if batch_id is not None:
        query = query.where(BatchLevel.batch_id == batch_id)
    return db.scalars(query).all()

@router.post('/levels', response_model=schemas.BatchLevelRead, status_code=201)
def create_level(
    p: schemas.BatchLevelCreate,
    user: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    batch = get_or_404(db, Batch, p.batch_id, 'Batch')
    if db.scalar(select(BatchLevel.id).where(
        BatchLevel.batch_id == batch.id,
        BatchLevel.level_number == p.level_number,
    )):
        raise HTTPException(409, f'Level {p.level_number} already exists for this batch')
    intake = resolve_intake(
        db,
        program_id=batch.program_id,
        code=p.intake_code,
        name=p.intake_name,
    )
    level = BatchLevel(batch_id=batch.id, level_number=p.level_number, intake_id=intake.id)
    return save_with_audit(
        db,
        level,
        user.id,
        'batch_level.created',
        'batch_level',
        p.model_dump(),
    )

@router.patch('/levels/{id}', response_model=schemas.BatchLevelRead)
def update_level(
    id: int,
    p: schemas.BatchLevelUpdate,
    user: Annotated[User, Depends(require_role('admin'))],
    db: DbSession,
):
    level = get_or_404(db, BatchLevel, id, 'Level')
    batch = get_or_404(db, Batch, level.batch_id, 'Batch')
    values = p.model_dump(exclude_unset=True)
    code = values.get('intake_code', level.intake.code)
    name = values.get('intake_name', level.intake.name)
    intake = resolve_intake(db, program_id=batch.program_id, code=code, name=name)
    if 'intake_name' in values:
        intake.name = (values['intake_name'] or '').strip() or None
    if intake.id != level.intake_id and db.scalar(
        select(CohortSemester.id).where(CohortSemester.batch_level_id == level.id)
    ):
        raise HTTPException(409, 'Cannot change the Intake Code after semesters exist for this level')
    before = {'intake_id': level.intake_id, 'intake_code': level.intake.code}
    level.intake_id = intake.id
    db.flush()
    log_audit(db, user.id, 'batch_level.updated', 'batch_level', level.id, before, values)
    db.commit()
    return db.scalar(
        select(BatchLevel)
        .options(selectinload(BatchLevel.intake))
        .where(BatchLevel.id == level.id)
    )

@router.post("/sections", response_model=schemas.SectionRead)
def create_section(p: schemas.SectionCreate, user: Annotated[User, Depends(require_role("admin"))], db: DbSession):
    values = p.model_dump()
    get_or_404(db, Batch, values['batch_id'], "Batch")
    if db.scalar(select(Section.id).where(
        Section.batch_id == values['batch_id'],
        func.lower(Section.name) == values['name'].strip().lower(),
    )):
        raise HTTPException(409, 'A section with that name already exists in this batch')
    values['name'] = values['name'].strip()
    section = Section(**values)
    db.add(section)
    db.flush()
    inherited = synchronize_section_module_offerings(db, section)
    after = values | {"inherited_module_offering_ids": [offering.id for offering in inherited]}
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
    section = get_or_404(db, Section, id, "Section")
    values = p.model_dump(exclude_none=True)
    if values.get('batch_id') is not None: get_or_404(db, Batch, values['batch_id'], "Batch")
    if 'batch_id' in values:
        if db.scalar(select(Student.id).where(Student.section_id == id)) or db.scalar(
            select(StudentEnrollment.id).where(StudentEnrollment.section_id == id)
        ):
            raise HTTPException(
                409,
                'This section has student history and cannot be moved to another batch.',
            )
    target_batch_id = values.get('batch_id', section.batch_id)
    target_name = values.get('name', section.name).strip()
    if db.scalar(select(Section.id).where(
        Section.batch_id == target_batch_id,
        func.lower(Section.name) == target_name.lower(),
        Section.id != id,
    )):
        raise HTTPException(409, 'A section with that name already exists in this batch')
    if 'name' in values:
        values['name'] = target_name
    for key, value in values.items():
        setattr(section, key, value)
    db.flush()
    synchronize_section_module_offerings(db, section)
    return save(db, section)
@router.delete("/sections/{id}", status_code=204)
def delete_section(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=get_or_404(db,Section,id,"Section")
    from .models import RoutineEntrySection
    if db.scalar(select(Student.id).where(Student.section_id==id)) or db.scalar(select(StudentEnrollment.id).where(StudentEnrollment.section_id==id)) or db.scalar(select(Subject.id).where(Subject.section_id==id)) or db.scalar(select(RoutineEntrySection.id).where(RoutineEntrySection.section_id==id)):raise HTTPException(409,"Cannot delete a section with student history, subjects, or routine entries")
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
    student = Student(
        user_id=user.id,
        section_id=p.section_id,
        roll_number=p.roll_number,
        name=p.name,
        email=str(p.email),
        subjects=subjects,
    )
    db.add(student)
    db.flush()
    from .promotion_service import ensure_student_enrollment
    ensure_student_enrollment(db, student)
    return save(db, student)
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
    from .models import RoutineEntry, TeacherFeedback
    if db.scalar(select(TeacherFeedback.id).where(TeacherFeedback.teacher_id == id)):
        raise HTTPException(409, "Remove the teacher's semester feedback forms before deleting this teacher")
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
