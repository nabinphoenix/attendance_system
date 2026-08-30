import hashlib
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from app.core.dependencies import DbSession, require_role
from app.modules.identity.models import User
from app.modules.operations.service import log_audit
from .models import InvitationPurpose, InvitationStatus, Section, Student, StudentInvitation
from .invitation_service import issue_student_invitation

router = APIRouter(prefix="/academic", tags=["student onboarding"])

def invitation_is_current(invite: StudentInvitation | None) -> bool:
    if not invite or invite.status != InvitationStatus.SENT:
        return False
    expires = invite.expires_at.replace(tzinfo=UTC) if invite.expires_at.tzinfo is None else invite.expires_at
    return expires > datetime.now(UTC)

def invitation_state(student: Student, invite: StudentInvitation | None) -> str:
    if invitation_is_current(invite):
        return "Password Setup Queued" if invite.purpose == InvitationPurpose.PASSWORD_SETUP else "Invitation Queued"
    if student.user_id:
        return "Activated"
    if not invite or invite.status in (InvitationStatus.REVOKED, InvitationStatus.ACTIVATED):
        return "Not Invited"
    return "Expired"

def read_student(student:Student,invite:StudentInvitation|None):
    return {"id":student.id,"name":student.name or (student.user.name if student.user else None),"email":student.email or (student.user.email if student.user else None),"roll_number":student.roll_number,"section_id":student.section_id,"section_name":student.section.name,"intake_id":student.section.intake_id,"semester_number":student.section.semester_number,"has_account":student.user_id is not None,"account_status":invitation_state(student,invite)}
@router.get("/students",dependencies=[Depends(require_role("admin"))])
def students(db:DbSession,intake_id:int|None=None,section_id:int|None=None,only_without_accounts:bool=False):
    q=select(Student).join(Section)
    if intake_id:q=q.where(Section.intake_id==intake_id)
    if section_id:q=q.where(Student.section_id==section_id)
    if only_without_accounts:q=q.where(Student.user_id.is_(None))
    records=[]
    for student in db.scalars(q.order_by(Student.id)).all():
        invite=db.scalar(select(StudentInvitation).where(StudentInvitation.student_id==student.id).order_by(StudentInvitation.id.desc()))
        records.append(read_student(student,invite))
    return records
class InvitationRequest(BaseModel):
    student_ids:list[int]=[]
    intake_id:int|None=None
    section_id:int|None=None
    only_without_accounts:bool=True
@router.post("/students/invitations",dependencies=[Depends(require_role("admin"))])
def send_invitations(payload:InvitationRequest,actor:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    q=select(Student).join(Section)
    if payload.student_ids:q=q.where(Student.id.in_(payload.student_ids))
    if payload.intake_id:q=q.where(Section.intake_id==payload.intake_id)
    if payload.section_id:q=q.where(Student.section_id==payload.section_id)
    if payload.only_without_accounts:q=q.where(Student.user_id.is_(None))
    requested=0;sent=0;activation_sent=0;password_setup_sent=0;failed=0;errors=[]
    for student in db.scalars(q).all():
        requested+=1
        try:
            account = student.user if student.user_id else None
            purpose = InvitationPurpose.PASSWORD_SETUP if account else InvitationPurpose.ACTIVATION
            issue_student_invitation(db, student, account)
            if purpose == InvitationPurpose.PASSWORD_SETUP:
                password_setup_sent += 1
            else:
                activation_sent += 1
            sent+=1
        except Exception as exc:failed+=1;errors.append({"student_id":student.id,"message":str(exc)})
    log_audit(db,actor.id,"student.invitations_sent","student_invitation",0,None,{"requested":requested,"sent":sent,"activation_sent":activation_sent,"password_setup_sent":password_setup_sent,"failed":failed});db.commit()
    return {"requested":requested,"sent":sent,"activation_sent":activation_sent,"password_setup_sent":password_setup_sent,"already_registered":0,"failed":failed,"errors":errors}
