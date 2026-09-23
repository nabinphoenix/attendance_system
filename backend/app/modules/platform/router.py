"""Platform administration. No college administrator may enter these routes."""
from datetime import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from app.core.database import Base
from app.core.dependencies import DbSession, require_role
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import UserRead
from app.modules.operations.models import AuditLog
from app.modules.operations.service import log_audit
from app.modules.identity.service import unlock_account, invalidate_reset
from app.modules.academic.models import Section, Student, Teacher
from .models import College, PlatformConfiguration

SuperAdmin = Annotated[User, Depends(require_role("super_admin"))]
router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(require_role("super_admin"))])

class CollegeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    contact_email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)

class CollegeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

class CollegeRead(CollegeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime

class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: Literal["admin", "teacher", "student", "coordinator", "parent"] = "admin"
    college_id: int
    employee_code: str | None = Field(default=None, min_length=1, max_length=50)
    section_id: int | None = None
    roll_number: str | None = Field(default=None, min_length=1, max_length=50)

class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    is_active: bool | None = None

class ConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    platform_name: str = Field(min_length=1, max_length=150)
    support_email: EmailStr | None = None
    allow_college_creation: bool = True


def save(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A record with these identifiers already exists, or related records prevent this operation") from exc


def college_or_404(db, college_id):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    return college


@router.get("/overview")
def overview(db: DbSession):
    return {
        "colleges": db.scalar(select(func.count()).select_from(College)),
        "active_colleges": db.scalar(select(func.count()).select_from(College).where(College.is_active.is_(True))),
        "users": db.scalar(select(func.count()).select_from(User)),
        "students": db.scalar(select(func.count()).select_from(Student)),
        "teachers": db.scalar(select(func.count()).select_from(Teacher)),
        "audit_events": db.scalar(select(func.count()).select_from(AuditLog)),
    }


@router.get("/colleges", response_model=list[CollegeRead])
def colleges(db: DbSession):
    return db.scalars(select(College).order_by(College.name)).all()


@router.post("/colleges", response_model=CollegeRead, status_code=201)
def create_college(payload: CollegeCreate, actor: SuperAdmin, db: DbSession):
    config = db.get(PlatformConfiguration, 1)
    if config and not config.allow_college_creation:
        raise HTTPException(403, "College creation is disabled in platform configuration")
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    if not values["name"]:
        raise HTTPException(422, "College name is required")
    if db.scalar(select(College.id).where(College.slug == payload.slug)):
        raise HTTPException(409, "This college slug is already in use")
    college = College(**values)
    db.add(college)
    db.flush()
    log_audit(db, actor.id, "college.created", "college", college.id, None, values)
    save(db)
    db.refresh(college)
    return college


@router.get("/colleges/{college_id}", response_model=CollegeRead)
def get_college(college_id: int, db: DbSession):
    return college_or_404(db, college_id)


@router.patch("/colleges/{college_id}", response_model=CollegeRead)
def update_college(college_id: int, payload: CollegeUpdate, actor: SuperAdmin, db: DbSession):
    college = college_or_404(db, college_id)
    values = payload.model_dump(exclude_unset=True)
    if "name" in values:
        if not values["name"] or not values["name"].strip():
            raise HTTPException(422, "College name is required")
        values["name"] = values["name"].strip()
    if "is_active" in values and values["is_active"] is None:
        raise HTTPException(422, "Active status is required")
    before = {key: getattr(college, key) for key in values}
    for key, value in values.items():
        setattr(college, key, value)
    log_audit(db, actor.id, "college.updated", "college", college.id, before, values)
    save(db)
    return college


@router.delete("/colleges/{college_id}", status_code=204)
def delete_college(college_id: int, actor: SuperAdmin, db: DbSession):
    college = college_or_404(db, college_id)
    # Never erase attendance, identities, or audit history as a side effect.
    for table in Base.metadata.tables.values():
        if "college_id" in table.c and db.connection().scalar(select(func.count()).select_from(table).where(table.c.college_id == college_id)):
            raise HTTPException(409, "This college contains data. Deactivate it to preserve its history.")
    log_audit(db, actor.id, "college.deleted", "college", college.id, {"name": college.name, "slug": college.slug}, None)
    db.delete(college)
    save(db)


@router.get("/users")
def accounts(db: DbSession, college_id: int | None = None, q: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    query = select(User)
    if college_id is not None:
        query = query.where(User.college_id == college_id)
    if q:
        query = query.where(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(User.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [UserRead.model_validate(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/users", response_model=UserRead, status_code=201)
def create_account(payload: AccountCreate, actor: SuperAdmin, db: DbSession):
    college = college_or_404(db, payload.college_id)
    if not college.is_active:
        raise HTTPException(409, "Reactivate the college before creating accounts")
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists")
    if payload.role == "teacher" and not payload.employee_code:
        raise HTTPException(422, "An employee code is required for teachers")
    if payload.role == "student":
        section = db.get(Section, payload.section_id) if payload.section_id else None
        if not section or section.college_id != college.id or not payload.roll_number:
            raise HTTPException(422, "Students require a section in this college and a roll number")
    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password), role=UserRole(payload.role), college_id=college.id)
    if not user.name:
        raise HTTPException(422, "Name is required")
    db.add(user)
    try:
        db.flush()
        if payload.role == "teacher":
            db.add(Teacher(user_id=user.id, employee_code=payload.employee_code, college_id=college.id))
        elif payload.role == "student":
            student = Student(user_id=user.id, section_id=payload.section_id, roll_number=payload.roll_number, name=user.name, email=user.email, college_id=college.id)
            db.add(student)
            db.flush()
            from app.modules.academic.promotion_service import ensure_student_enrollment
            # Enrollment services inherit the college of the new student.
            db.info["college_id"] = college.id
            ensure_student_enrollment(db, student)
            db.flush()
            db.info["college_id"] = None
        log_audit(db, actor.id, "platform.user_created", "user", user.id, None, {"email": email, "role": payload.role, "college_id": college.id})
        save(db)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email, employee code, or roll number is already in use") from exc
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_account(user_id: int, payload: AccountUpdate, actor: SuperAdmin, db: DbSession):
    account = db.get(User, user_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if account.role == UserRole.SUPER_ADMIN and account.id != actor.id:
        raise HTTPException(403, "Other platform accounts cannot be edited here")
    values = payload.model_dump(exclude_none=True)
    if account.id == actor.id and values.get("is_active") is False:
        raise HTTPException(422, "You cannot deactivate your own account")
    before = {key: getattr(account, key) for key in values if key != "password"}
    for key, value in values.items():
        if key == "password":
            account.password_hash = hash_password(value)
            account.session_version += 1
            invalidate_reset(account)
        else:
            value = str(value).lower() if key == "email" else value
            if key == "name":
                value = value.strip()
                if not value: raise HTTPException(422, "Name is required")
            setattr(account, key, value)
            if key == "email": invalidate_reset(account)
    student = db.scalar(select(Student).where(Student.user_id == account.id))
    if student:
        student.name, student.email = account.name, account.email
    safe_changes = {key: value for key, value in values.items() if key != "password"}
    if "password" in values: safe_changes["password_reset"] = True
    log_audit(db, actor.id, "platform.user_updated", "user", account.id, before, safe_changes)
    save(db)
    return account


@router.post("/users/{user_id}/unlock", response_model=UserRead)
def unlock_platform_account(user_id: int, actor: SuperAdmin, db: DbSession):
    account = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not account:
        raise HTTPException(404, "Account not found")
    return unlock_account(db, account, actor)


@router.delete("/users/{user_id}", status_code=204)
def delete_account(user_id: int, actor: SuperAdmin, db: DbSession):
    account = db.get(User, user_id)
    if not account: raise HTTPException(404, "Account not found")
    if account.role == UserRole.SUPER_ADMIN: raise HTTPException(422, "Platform accounts cannot be deleted here")
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == "users" and db.connection().scalar(select(func.count()).select_from(table).where(fk.parent == user_id)):
                raise HTTPException(409, "This account has linked records. Deactivate it to preserve its history.")
    log_audit(db, actor.id, "platform.user_deleted", "user", user_id, {"email": account.email, "college_id": account.college_id}, None)
    db.delete(account)
    save(db)


@router.get("/audit-logs")
def audit_logs(db: DbSession, college_id: int | None = None, action: str = "", actor_id: int | None = None, date_from: datetime | None = None, date_to: datetime | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    query = select(AuditLog, User.name, College.name).outerjoin(User, AuditLog.actor_id == User.id).outerjoin(College, AuditLog.college_id == College.id)
    if college_id is not None: query = query.where(AuditLog.college_id == college_id)
    if action: query = query.where(AuditLog.action.ilike(f"%{action}%"))
    if actor_id is not None: query = query.where(AuditLog.actor_id == actor_id)
    if date_from: query = query.where(AuditLog.created_at >= date_from)
    if date_to: query = query.where(AuditLog.created_at <= date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [{"id": a.id, "college_id": a.college_id, "college_name": college_name, "actor_id": a.actor_id, "actor_name": actor_name, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "details": a.details, "created_at": a.created_at} for a, actor_name, college_name in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/configuration", response_model=ConfigurationRead)
def configuration(db: DbSession):
    return db.get(PlatformConfiguration, 1) or ConfigurationRead(platform_name="AntimBench")


@router.put("/configuration", response_model=ConfigurationRead)
def update_configuration(payload: ConfigurationRead, actor: SuperAdmin, db: DbSession):
    if not payload.platform_name.strip(): raise HTTPException(422, "Platform name is required")
    config = db.get(PlatformConfiguration, 1)
    before = ConfigurationRead.model_validate(config).model_dump() if config else None
    if config is None:
        config = PlatformConfiguration(id=1)
        db.add(config)
    for key, value in payload.model_dump().items(): setattr(config, key, value)
    log_audit(db, actor.id, "platform.configuration_updated", "platform_configuration", 1, before, payload.model_dump())
    save(db)
    return config
