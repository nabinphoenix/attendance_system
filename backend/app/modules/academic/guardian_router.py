from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.core.dependencies import DbSession,require_role
from app.modules.identity.models import User
from app.modules.operations.models import Notification
from app.modules.operations.schemas import NotificationRead
from .models import Guardian,Student
from .schemas import StudentRead
router=APIRouter(prefix="/guardians/me",tags=["guardians"])
Parent=Annotated[User,Depends(require_role("parent"))]
@router.get("/students",response_model=list[StudentRead])
def students(user:Parent,db:DbSession):return db.scalars(select(Student).join(Guardian).where(Guardian.user_id==user.id)).all()
@router.get("/notifications",response_model=list[NotificationRead])
def notifications(user:Parent,db:DbSession):
    guardian_ids=db.scalars(select(Guardian.id).where(Guardian.user_id==user.id)).all()
    return db.scalars(select(Notification).where(Notification.recipient_type=="guardian",Notification.recipient_id.in_(guardian_ids)).order_by(Notification.created_at.desc())).all()
