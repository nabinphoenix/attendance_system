import io,json
import pandas as pd
from typing import Annotated
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from sqlalchemy import func,select
from app.core.dependencies import DbSession,require_role
from app.core.security import hash_password
from app.modules.academic.models import Batch,Guardian,Section,Student
from app.modules.identity.models import User,UserRole
from .models import ImportJob
from .schemas import ImportError,ImportJobRead
router=APIRouter(tags=["operations"])
DEFAULT_PASSWORD="Welcome123!"
def read_job(job):return ImportJobRead(id=job.id,file_name=job.file_name,upload_type=job.upload_type,total_rows=job.total_rows,success_count=job.success_count,failed_count=job.failed_count,errors=[ImportError(**e) for e in json.loads(job.errors_json)],created_at=job.created_at)
@router.post("/imports/students",response_model=ImportJobRead)
async def import_students(user:Annotated[User,Depends(require_role("admin"))],db:DbSession,file:UploadFile=File(...)):
    try:frame=pd.read_csv(io.BytesIO(await file.read()),dtype=str).fillna("")
    except Exception as exc:raise HTTPException(400,"Invalid CSV file") from exc
    job=ImportJob(uploaded_by=user.id,file_name=file.filename or "students.csv",upload_type="students",total_rows=len(frame),success_count=0,failed_count=0);db.add(job);db.flush();errors=[]
    for offset,row in frame.iterrows():
        row_number=int(offset)+2
        try:
            with db.begin_nested():
                name=str(row.get("name","")).strip();email=str(row.get("email","")).strip().lower();batch_name=str(row.get("batch_name","")).strip();section_name=str(row.get("section_name","")).strip()
                if not name:raise ValueError("name is required")
                if not email:raise ValueError("email is required")
                if db.scalar(select(User).where(func.lower(User.email)==email)):raise ValueError("email is already in use")
                section=db.scalar(select(Section).join(Batch).where(func.lower(Batch.name)==batch_name.lower(),func.lower(Section.name)==section_name.lower()))
                if not section:raise ValueError("batch_name or section_name does not exist")
                account=User(name=name,email=email,password_hash=hash_password(DEFAULT_PASSWORD),role=UserRole.STUDENT);db.add(account);db.flush();student=Student(user_id=account.id,section_id=section.id,roll_number=f"IMP-{job.id}-{row_number}");db.add(student);db.flush();phone=str(row.get("phone","")).strip()
                if phone:db.add(Guardian(name=f"Guardian of {name} ({phone})",student_id=student.id))
            job.success_count+=1
        except Exception as exc:
            errors.append({"row_number":row_number,"error_message":str(exc)});job.failed_count+=1
    job.errors_json=json.dumps(errors);db.commit();db.refresh(job);return read_job(job)
@router.get("/imports",response_model=list[ImportJobRead])
def import_history(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return [read_job(j) for j in db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc())).all()]
@router.get("/imports/{id}",response_model=ImportJobRead)
def import_detail(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    job=db.get(ImportJob,id)
    if not job:raise HTTPException(404,"Import job not found")
    return read_job(job)
@router.get("/operations/health")
def health():return {"module":"operations","status":"ok"}
