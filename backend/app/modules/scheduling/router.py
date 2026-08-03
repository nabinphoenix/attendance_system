from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.core.dependencies import DbSession, get_current_user, require_role
from app.modules.academic.models import Teacher
from app.modules.identity.models import User
from .models import ClassSession, ScheduleOverride, SessionStatus, TimetableEntry
from .schemas import ClassSessionRead, CurrentSession, TimetableCreate, TimetableRead
router = APIRouter(tags=["scheduling"])
@router.post("/scheduling/timetable-entries", response_model=TimetableRead, dependencies=[Depends(require_role("admin"))])
def create_entry(p: TimetableCreate, db: DbSession):
    obj=TimetableEntry(**p.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return obj
@router.get("/teachers/me/current-sessions", response_model=list[CurrentSession])
def current_sessions(user: Annotated[User, Depends(require_role("teacher"))], db: DbSession):
    teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
    if not teacher: raise HTTPException(404,"Teacher profile not found")
    now=datetime.now(); entries=db.scalars(select(TimetableEntry).where(TimetableEntry.teacher_id==teacher.id, TimetableEntry.day_of_week==now.weekday())).all(); result=[]
    for entry in entries:
        override=db.scalar(select(ScheduleOverride).where(ScheduleOverride.timetable_entry_id==entry.id, ScheduleOverride.override_date==now.date()))
        if override and override.is_cancelled: continue
        start=override.start_time if override and override.start_time else entry.start_time; end=override.end_time if override and override.end_time else entry.end_time
        if start <= now.time() <= end:
            session=db.scalar(select(ClassSession).where(ClassSession.timetable_entry_id==entry.id,ClassSession.session_date==now.date()))
            result.append(CurrentSession(timetable_entry_id=entry.id,subject_name=entry.subject.name,room_name=entry.room_name,start_time=start,end_time=end,class_session_id=session.id if session else None,status=session.status.value if session else None))
    return result
@router.post("/sessions/{entry_id}/start", response_model=ClassSessionRead)
def start_session(entry_id:int,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id)); entry=db.get(TimetableEntry,entry_id)
    if not entry or not teacher or entry.teacher_id!=teacher.id: raise HTTPException(403,"Not your timetable entry")
    today=datetime.now().date(); session=db.scalar(select(ClassSession).where(ClassSession.timetable_entry_id==entry_id,ClassSession.session_date==today))
    if not session: session=ClassSession(timetable_entry_id=entry_id,session_date=today,status=SessionStatus.ACTIVE); db.add(session); db.commit(); db.refresh(session)
    return session
