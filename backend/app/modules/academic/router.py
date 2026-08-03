from typing import Annotated, TypeVar
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.dependencies import DbSession, require_role
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from . import schemas
from .models import Batch, Guardian, Program, Section, Student, Subject, Teacher

router = APIRouter(prefix="/academic", tags=["academic"], dependencies=[Depends(require_role("admin"))])
T = TypeVar("T")
def save(db: Session, obj: T) -> T:
    db.add(obj); db.commit(); db.refresh(obj); return obj
def create_user(db: Session, name: str, email: str, password: str, role: UserRole) -> User:
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user); db.flush(); return user

@router.post("/programs", response_model=schemas.ProgramRead)
def create_program(p: schemas.ProgramCreate, db: DbSession): return save(db, Program(**p.model_dump()))
@router.post("/batches", response_model=schemas.BatchRead)
def create_batch(p: schemas.BatchCreate, db: DbSession): return save(db, Batch(**p.model_dump()))
@router.post("/sections", response_model=schemas.SectionRead)
def create_section(p: schemas.SectionCreate, db: DbSession): return save(db, Section(**p.model_dump()))
@router.post("/subjects", response_model=schemas.SubjectRead)
def create_subject(p: schemas.SubjectCreate, db: DbSession): return save(db, Subject(**p.model_dump()))
@router.post("/guardians", response_model=schemas.GuardianRead)
def create_guardian(p: schemas.GuardianCreate, db: DbSession): return save(db, Guardian(**p.model_dump()))
@router.post("/students", response_model=schemas.StudentRead)
def create_student(p: schemas.StudentCreate, db: DbSession):
    user = create_user(db, p.name, p.email, p.password, UserRole.STUDENT)
    subjects = [db.get(Subject, i) for i in p.subject_ids]
    if any(x is None for x in subjects): raise HTTPException(404, "Subject not found")
    return save(db, Student(user_id=user.id, section_id=p.section_id, roll_number=p.roll_number, subjects=subjects))
@router.post("/teachers", response_model=schemas.TeacherRead)
def create_teacher(p: schemas.TeacherCreate, db: DbSession):
    user = create_user(db, p.name, p.email, p.password, UserRole.TEACHER)
    return save(db, Teacher(user_id=user.id, employee_code=p.employee_code))
@router.get("/students/{id}", response_model=schemas.StudentRead)
def get_student(id: int, db: DbSession):
    if not (obj := db.get(Student, id)): raise HTTPException(404, "Student not found")
    return obj
@router.get("/teachers/{id}", response_model=schemas.TeacherRead)
def get_teacher(id: int, db: DbSession):
    if not (obj := db.get(Teacher, id)): raise HTTPException(404, "Teacher not found")
    return obj
@router.get("/teachers",response_model=list[schemas.TeacherRead])
def teachers(db:DbSession):return db.scalars(select(Teacher)).all()
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
