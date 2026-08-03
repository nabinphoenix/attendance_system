from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.core.dependencies import DbSession, require_role, require_roles
from app.modules.academic.models import Student, StudentSubjectEnrollment, Teacher
from app.modules.identity.models import User
from app.modules.operations.models import AuditLog
from app.modules.scheduling.models import ClassSession, SessionStatus
from .models import AttendanceChange,AttendanceMethod,AttendanceRecord,AttendanceStatus,LeaveRequest
from .schemas import CheckInRequest,CheckInResponse,QRResponse,RosterItem,StatusChange
from .service import distance_meters,generate_qr_token,validate_qr_token
router=APIRouter(tags=["attendance"])
def teacher_session(db,user,session_id):
    session=db.get(ClassSession,session_id); teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
    if not session or not teacher or session.effective_teacher_id!=teacher.id: raise HTTPException(403,"Not your class session")
    return session
@router.get("/sessions/{id}/qr",response_model=QRResponse)
def qr(id:int,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    session=teacher_session(db,user,id)
    if session.status!=SessionStatus.ACTIVE: raise HTTPException(409,"Session is not active")
    now=datetime.now(UTC); expires=session.qr_expires_at
    if not session.current_qr_token or not expires or (expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires)<=now:
        session.current_qr_token,session.qr_expires_at=generate_qr_token(id); db.commit(); expires=session.qr_expires_at
    return QRResponse(token=session.current_qr_token,expires_at=expires,expires_in_seconds=settings.qr_token_expire_seconds)
@router.post("/check-ins",response_model=CheckInResponse)
def check_in(p:CheckInRequest,user:Annotated[User,Depends(require_role("student"))],db:DbSession):
    student=db.scalar(select(Student).where(Student.user_id==user.id))
    if not student: raise HTTPException(404,"Student profile not found")
    try: session_id=validate_qr_token(p.qr_token)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    session=db.get(ClassSession,session_id)
    if not session or session.status!=SessionStatus.ACTIVE: raise HTTPException(409,"Session is not active")
    entry=session.timetable_entry
    enrolled=db.scalar(select(StudentSubjectEnrollment).where(StudentSubjectEnrollment.student_id==student.id,StudentSubjectEnrollment.subject_id==entry.subject_id))
    if student.section_id!=entry.section_id or not enrolled: raise HTTPException(403,"Student is not enrolled in this class")
    existing=db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id==session.id,AttendanceRecord.student_id==student.id))
    if existing: raise HTTPException(409,"Student has already checked in")
    if p.accuracy>settings.geolocation_max_accuracy_meters: raise HTTPException(400,"Location accuracy is too low; get a fresh GPS reading")
    distance=distance_meters(p.latitude,p.longitude,entry.latitude,entry.longitude)
    if distance>settings.geofence_radius_meters: raise HTTPException(403,f"Outside attendance geofence ({distance:.0f}m away)")
    record=AttendanceRecord(class_session_id=session.id,student_id=student.id,status=AttendanceStatus.PRESENT,method=AttendanceMethod.QR_GEOFENCE,check_in_time=datetime.now(UTC)); db.add(record); db.commit(); db.refresh(record)
    return CheckInResponse(attendance_id=record.id,status=record.status.value,check_in_time=record.check_in_time)
@router.get("/sessions/{id}/attendance",response_model=list[RosterItem])
def roster(id:int,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    session=teacher_session(db,user,id); entry=session.timetable_entry
    students=db.scalars(select(Student).join(StudentSubjectEnrollment).where(Student.section_id==entry.section_id,StudentSubjectEnrollment.subject_id==entry.subject_id)).all(); result=[]
    for student in students:
        record=db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id==id,AttendanceRecord.student_id==student.id))
        result.append(RosterItem(attendance_id=record.id if record else None,student_id=student.id,student_name=student.user.name,roll_number=student.roll_number,status=record.status.value if record else "pending"))
    return result
@router.get("/sessions/{id}/summary",response_model=list[RosterItem])
def summary(id:int,user:Annotated[User,Depends(require_roles("teacher","admin"))],db:DbSession):
    session=db.get(ClassSession,id)
    if not session:raise HTTPException(404,"Session not found")
    if user.role.value=="teacher":teacher_session(db,user,id)
    entry=session.timetable_entry;students=db.scalars(select(Student).join(StudentSubjectEnrollment).where(Student.section_id==entry.section_id,StudentSubjectEnrollment.subject_id==entry.subject_id)).all();result=[]
    for student in students:
        record=db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id==id,AttendanceRecord.student_id==student.id));result.append(RosterItem(attendance_id=record.id if record else None,student_id=student.id,student_name=student.user.name,roll_number=student.roll_number,status=record.status.value if record else "pending"))
    return result
@router.post("/sessions/{id}/finalize",response_model=list[RosterItem])
def finalize(id:int,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    session=teacher_session(db,user,id); entry=session.timetable_entry
    students=db.scalars(select(Student).join(StudentSubjectEnrollment).where(Student.section_id==entry.section_id,StudentSubjectEnrollment.subject_id==entry.subject_id)).all()
    for student in students:
        record=db.scalar(select(AttendanceRecord).where(AttendanceRecord.class_session_id==id,AttendanceRecord.student_id==student.id))
        if not record:
            leave=db.scalar(select(LeaveRequest).where(LeaveRequest.student_id==student.id,LeaveRequest.leave_date==session.session_date,LeaveRequest.status=="approved"))
            db.add(AttendanceRecord(class_session_id=id,student_id=student.id,status=AttendanceStatus.LEAVE if leave else AttendanceStatus.ABSENT,method=AttendanceMethod.FINALIZATION))
    session.status=SessionStatus.COMPLETED; session.finalized_at=datetime.now(UTC); db.commit(); return roster(id,user,db)
@router.patch("/attendance/{id}",response_model=RosterItem)
def change_status(id:int,p:StatusChange,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    if not p.reason.strip(): raise HTTPException(422,"Reason is required")
    record=db.get(AttendanceRecord,id)
    if not record: raise HTTPException(404,"Attendance record not found")
    teacher_session(db,user,record.class_session_id)
    try: new=AttendanceStatus(p.status.lower())
    except ValueError as exc: raise HTTPException(422,"Invalid status") from exc
    old=record.status; db.add(AttendanceChange(attendance_record_id=id,before_status=old,after_status=new,reason=p.reason,actor_id=user.id)); db.add(AuditLog(actor_id=user.id,action="attendance.status_changed",entity_type="attendance_record",entity_id=id,details=f"{old.value} -> {new.value}: {p.reason}")); record.status=new; record.method=AttendanceMethod.MANUAL; db.commit(); student=db.get(Student,record.student_id)
    return RosterItem(attendance_id=record.id,student_id=student.id,student_name=student.user.name,roll_number=student.roll_number,status=record.status.value)
