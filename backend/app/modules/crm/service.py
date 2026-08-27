from datetime import UTC,datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.crm.models import CasePriority,CaseStatus,StudentCase
def priority_for(percent:float)->CasePriority:return CasePriority.HIGH if percent<50 else CasePriority.MEDIUM if percent<65 else CasePriority.LOW
def get_or_create_attendance_case(db:Session,student_id:int,scope_type:str,scope_id:int,attendance_percent:float)->tuple[StudentCase,bool]:
    case=db.scalar(select(StudentCase).where(StudentCase.student_id==student_id,StudentCase.trigger_type=="ATTENDANCE_LOW",StudentCase.scope_type==scope_type,StudentCase.scope_id==scope_id,StudentCase.status.in_([CaseStatus.OPEN,CaseStatus.IN_PROGRESS])))
    if case:case.last_evaluated_at=datetime.now(UTC);return case,False
    case=StudentCase(student_id=student_id,trigger_type="ATTENDANCE_LOW",scope_type=scope_type,scope_id=scope_id,status=CaseStatus.OPEN,priority=priority_for(attendance_percent));db.add(case);db.flush();return case,True
