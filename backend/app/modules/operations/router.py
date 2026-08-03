import io,json
from datetime import UTC,date,datetime
from typing import Annotated
import pandas as pd
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from fastapi.responses import StreamingResponse
from jinja2 import Template
from sqlalchemy import func,or_,select
from app.core.config import settings
from app.core.dependencies import DbSession,get_current_user,require_role
from app.core.security import hash_password
from app.modules.academic.models import Batch,Guardian,Section,Student,Subject,Teacher
from app.modules.attendance.models import AttendanceRecord,AttendanceStatus
from app.modules.course_completion.models import CoursePlan
from app.modules.crm.models import CaseStatus,StudentCase
from app.modules.identity.models import User,UserRole
from app.modules.scheduling.models import ClassSession,TimetableEntry
from .models import AuditLog,ImportJob,Notification,NotificationStatus
from .schemas import AuditPage,AuditRead,ImportError,ImportJobRead,NotificationRead
from .service import log_audit
router=APIRouter(tags=["operations"]);DEFAULT_PASSWORD="Welcome123!"
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
                if phone:db.add(Guardian(name=f"Guardian of {name}",student_id=student.id,phone=phone))
            job.success_count+=1
        except Exception as exc:errors.append({"row_number":row_number,"error_message":str(exc)});job.failed_count+=1
    job.errors_json=json.dumps(errors);log_audit(db,user.id,"import.completed","import_job",job.id,None,{"success":job.success_count,"failed":job.failed_count});db.commit();db.refresh(job);return read_job(job)
@router.get("/imports",response_model=list[ImportJobRead])
def import_history(user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return [read_job(j) for j in db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc())).all()]
@router.get("/imports/{id}",response_model=ImportJobRead)
def import_detail(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    job=db.get(ImportJob,id)
    if not job:raise HTTPException(404,"Import job not found")
    return read_job(job)
def attendance_frame(db,user,student_id,section_id,batch_id,date_from,date_to):
    if date_from>date_to:raise HTTPException(422,"date_from must not exceed date_to")
    if user.role==UserRole.STUDENT:
        own=db.scalar(select(Student).where(Student.user_id==user.id))
        if not own:raise HTTPException(404,"Student profile not found")
        if student_id and student_id!=own.id:raise HTTPException(403,"Students may only export their own attendance")
        student_id=own.id
    q=select(AttendanceRecord.id,Student.id.label("student_id"),User.name.label("student_name"),Student.roll_number,Subject.name.label("subject"),ClassSession.session_date,AttendanceRecord.status,AttendanceRecord.check_in_time).join(Student,AttendanceRecord.student_id==Student.id).join(User,Student.user_id==User.id).join(ClassSession,AttendanceRecord.class_session_id==ClassSession.id).join(TimetableEntry,ClassSession.timetable_entry_id==TimetableEntry.id).join(Subject,TimetableEntry.subject_id==Subject.id).join(Section,Student.section_id==Section.id).where(ClassSession.session_date.between(date_from,date_to))
    if user.role==UserRole.TEACHER:
        teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id));allowed=select(TimetableEntry.section_id).where(TimetableEntry.teacher_id==teacher.id)
        q=q.where(Student.section_id.in_(allowed))
    if student_id:q=q.where(Student.id==student_id)
    if section_id:q=q.where(Student.section_id==section_id)
    if batch_id:q=q.where(Section.batch_id==batch_id)
    rows=db.execute(q.order_by(ClassSession.session_date,User.name)).mappings().all();frame=pd.DataFrame(rows)
    if len(frame):frame["status"]=frame["status"].map(lambda value:value.value if hasattr(value,"value") else str(value))
    return frame
def stream_bytes(data:bytes,media:str,filename:str):return StreamingResponse(io.BytesIO(data),media_type=media,headers={"Content-Disposition":f'attachment; filename="{filename}"'})
def render_pdf(html:str,title:str,lines:list[str],frame:pd.DataFrame)->bytes:
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except Exception:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        output=io.BytesIO();doc=SimpleDocTemplate(output,pagesize=landscape(A4));styles=getSampleStyleSheet();story=[Paragraph(settings.college_name,styles["Title"]),Paragraph(title,styles["Heading2"])]
        for line in lines:story.extend([Paragraph(line,styles["BodyText"]),Spacer(1,5)])
        data=[list(frame.columns)]+[[str(value) for value in row] for row in frame.itertuples(index=False,name=None)]
        if data:table=Table(data,repeatRows=1);table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#d1fae5")),("GRID",(0,0),(-1,-1),0.5,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)]));story.append(table)
        doc.build(story);return output.getvalue()
@router.get("/exports/attendance.csv")
def attendance_csv(user:Annotated[User,Depends(get_current_user)],db:DbSession,date_from:date,date_to:date,student_id:int|None=None,section_id:int|None=None,batch_id:int|None=None):return stream_bytes(attendance_frame(db,user,student_id,section_id,batch_id,date_from,date_to).to_csv(index=False).encode(),"text/csv","attendance_report.csv")
@router.get("/exports/attendance.pdf")
def attendance_pdf(user:Annotated[User,Depends(get_current_user)],db:DbSession,date_from:date,date_to:date,student_id:int|None=None,section_id:int|None=None,batch_id:int|None=None):
    frame=attendance_frame(db,user,student_id,section_id,batch_id,date_from,date_to);passing=frame["status"].astype(str).str.lower().isin(["attendancestatus.present","attendancestatus.late","present","late"]).sum() if len(frame) else 0;percent=round(100*passing/len(frame),2) if len(frame) else 0;generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC");html=Template("""<html><head><style>body{font-family:sans-serif}h1{color:#064e3b}table{width:100%;border-collapse:collapse}th,td{border:1px solid #aaa;padding:6px;font-size:11px}th{background:#d1fae5}</style></head><body><h1>{{college}}</h1><h2>Attendance Report</h2><p>Generated {{generated}} · {{date_from}} to {{date_to}}</p><p><b>Overall attendance: {{percent}}%</b> ({{passing}}/{{total}})</p>{{table|safe}}</body></html>""").render(college=settings.college_name,generated=generated,date_from=date_from,date_to=date_to,percent=percent,passing=passing,total=len(frame),table=frame.to_html(index=False));pdf=render_pdf(html,"Attendance Report",[f"Generated {generated}",f"Filters: {date_from} to {date_to}",f"Overall attendance: {percent}% ({passing}/{len(frame)})"],frame);return stream_bytes(pdf,"application/pdf","attendance_report.pdf")
def case_frame(db,status,date_from,date_to):
    q=select(StudentCase.id,StudentCase.student_id,StudentCase.trigger_type,StudentCase.scope_type,StudentCase.scope_id,StudentCase.status,StudentCase.priority,StudentCase.assigned_to,StudentCase.opened_at,StudentCase.closed_at)
    if status:q=q.where(StudentCase.status==CaseStatus(status))
    if date_from:q=q.where(func.date(StudentCase.opened_at)>=date_from)
    if date_to:q=q.where(func.date(StudentCase.opened_at)<=date_to)
    return pd.DataFrame(db.execute(q).mappings().all())
@router.get("/exports/cases.csv",dependencies=[Depends(require_role("admin"))])
def cases_csv(db:DbSession,status:str|None=None,date_from:date|None=None,date_to:date|None=None):return stream_bytes(case_frame(db,status,date_from,date_to).to_csv(index=False).encode(),"text/csv","case_report.csv")
@router.get("/exports/cases.pdf",dependencies=[Depends(require_role("admin"))])
def cases_pdf(db:DbSession,status:str|None=None,date_from:date|None=None,date_to:date|None=None):
    frame=case_frame(db,status,date_from,date_to);generated=f"{datetime.now(UTC):%Y-%m-%d}";html=f"<h1>{settings.college_name}</h1><h2>Student Case Report</h2><p>Generated {generated}</p>{frame.to_html(index=False)}";return stream_bytes(render_pdf(html,"Student Case Report",[f"Generated {generated}"],frame),"application/pdf","case_report.pdf")
@router.get("/exports/course-completion.csv",dependencies=[Depends(require_role("admin"))])
def course_csv(db:DbSession):
    rows=db.execute(select(CoursePlan.id,Subject.name.label("subject"),Batch.name.label("batch"),CoursePlan.planned_sessions,CoursePlan.conducted_sessions).join(Subject).join(Batch)).mappings().all();frame=pd.DataFrame(rows);frame["deficit"]=frame.planned_sessions-frame.conducted_sessions if len(frame) else [];return stream_bytes(frame.to_csv(index=False).encode(),"text/csv","course_completion.csv")
@router.get("/notifications",response_model=list[NotificationRead])
def notifications(user:Annotated[User,Depends(require_role("admin"))],db:DbSession,recipient_id:int|None=None,status:str|None=None):
    q=select(Notification)
    if recipient_id:q=q.where(Notification.recipient_id==recipient_id)
    if status:q=q.where(Notification.status==NotificationStatus(status))
    return db.scalars(q.order_by(Notification.created_at.desc())).all()
@router.get("/audit-logs",response_model=AuditPage)
def audit_logs(user:Annotated[User,Depends(require_role("admin"))],db:DbSession,actor_id:int|None=None,entity:str|None=None,date_from:date|None=None,date_to:date|None=None,page:int=1,page_size:int=50):
    q=select(AuditLog,User.name).join(User,AuditLog.actor_id==User.id)
    if actor_id:q=q.where(AuditLog.actor_id==actor_id)
    if entity:q=q.where(AuditLog.entity_type==entity)
    if date_from:q=q.where(func.date(AuditLog.created_at)>=date_from)
    if date_to:q=q.where(func.date(AuditLog.created_at)<=date_to)
    total=db.scalar(select(func.count()).select_from(q.subquery())) or 0;rows=db.execute(q.order_by(AuditLog.created_at.desc()).offset((page-1)*page_size).limit(min(page_size,100))).all();return AuditPage(items=[AuditRead(id=a.id,actor_id=a.actor_id,actor_name=n,action=a.action,entity_type=a.entity_type,entity_id=a.entity_id,details=a.details,created_at=a.created_at) for a,n in rows],total=total,page=page,page_size=page_size)
@router.get("/operations/health")
def health():return {"module":"operations","status":"ok"}
