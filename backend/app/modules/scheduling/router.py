from datetime import UTC,date,datetime
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import or_,select
from app.core.dependencies import DbSession,require_role,require_roles
from app.core.config import settings
from app.modules.academic.models import RoutineEntry, Section, Subject, Teacher
from app.modules.identity.models import User
from .models import ClassSession,OverrideStatus,ScheduleOverride,SessionStatus,TimetableEntry
from .schemas import ClassSessionRead,CurrentSession,OverrideCreate,OverrideDecision,OverrideRead,SessionGeofenceCapture,SessionHistory,TimetableCreate,TimetableRead
from .service import approved_routine_override,create_schedule_override,resolve_effective_class,resolve_session_schedule
from app.modules.operations.service import log_audit
router=APIRouter(tags=["scheduling"])
def approved_override(db,entry_id,on_date):return db.scalar(select(ScheduleOverride).where(ScheduleOverride.timetable_entry_id==entry_id,ScheduleOverride.override_date==on_date,ScheduleOverride.status==OverrideStatus.APPROVED))
def teacher_profile(db,user):
    teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
    if not teacher:raise HTTPException(404,"Teacher profile not found")
    return teacher
@router.post("/routine-sessions/{routine_id}/start",response_model=ClassSessionRead)
def start_routine_session(routine_id:int,p:SessionGeofenceCapture,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    teacher=teacher_profile(db,user);entry=db.get(RoutineEntry,routine_id)
    if not entry:raise HTTPException(404,"Routine entry not found")
    today=datetime.now().date()
    override=approved_routine_override(db,entry.id,today)
    if entry.day_of_week!=today.weekday() and not (override and override.is_makeup):raise HTTPException(409,"This routine is not scheduled today")
    effective=resolve_effective_class(db,entry,today,override)
    if effective.cancelled:raise HTTPException(409,"Class is cancelled")
    if effective.teacher_id!=teacher.id:raise HTTPException(403,"This session is assigned to another teacher")
    session=db.scalar(select(ClassSession).where(ClassSession.routine_entry_id==routine_id,ClassSession.session_date==today))
    if not session:
        captured_at=datetime.now(UTC);radius=p.geofence_radius_meters or settings.geofence_radius_meters
        # GPS is retained as coarse campus/audit evidence. It must not block an
        # authorized teacher from starting a session because indoor readings
        # commonly report wide accuracy circles (for example, +/-69m).
        session=ClassSession(routine_entry_id=routine_id,session_date=today,effective_teacher_id=effective.teacher_id,effective_room=effective.room,schedule_override_id=effective.override_id,status=SessionStatus.ACTIVE,geofence_latitude=p.latitude,geofence_longitude=p.longitude,geofence_radius_meters=radius,teacher_location_accuracy_meters=p.accuracy_meters,geofence_captured_at=captured_at,self_checkin_window_minutes=p.self_checkin_window_minutes or settings.attendance_self_checkin_window_minutes,challenge_rotation_seconds=p.challenge_rotation_seconds or settings.attendance_challenge_rotation_seconds);db.add(session);db.flush();log_audit(db,user.id,"class_session.started","class_session",session.id,None,{"routine_entry_id":routine_id,"geofence_created":True,"geofence_radius_meters":radius,"teacher_location_accuracy_meters":p.accuracy_meters,"geofence_captured_at":captured_at,"self_checkin_window_minutes":session.self_checkin_window_minutes,"challenge_rotation_seconds":session.challenge_rotation_seconds});db.commit();db.refresh(session)
    return session
@router.post("/scheduling/timetable-entries",response_model=TimetableRead,dependencies=[Depends(require_role("admin"))])
def create_entry(p:TimetableCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    raise HTTPException(410,"Legacy TimetableEntry creation is deprecated; use canonical routines")
    if p.start_time >= p.end_time: raise HTTPException(422,"end_time must be after start_time")
    if not db.get(Teacher,p.teacher_id): raise HTTPException(404,"Teacher not found")
    section=db.get(Section,p.section_id);subject=db.get(Subject,p.subject_id)
    if not section: raise HTTPException(404,"Section not found")
    if not subject or subject.section_id!=section.id: raise HTTPException(422,"Subject must belong to the selected section")
    obj=TimetableEntry(**p.model_dump());db.add(obj);db.flush();log_audit(db,user.id,"timetable_entry.created","timetable_entry",obj.id,None,p.model_dump());db.commit();db.refresh(obj);return obj
@router.get("/scheduling/timetable-entries",response_model=list[TimetableRead])
def entries(user:Annotated[User,Depends(require_role("admin"))],db:DbSession,batch_id:int|None=None,section_id:int|None=None):
    q=select(TimetableEntry).join(Section,TimetableEntry.section_id==Section.id)
    if batch_id is not None:q=q.where(Section.batch_id==batch_id)
    if section_id is not None:q=q.where(TimetableEntry.section_id==section_id)
    return db.scalars(q.order_by(TimetableEntry.day_of_week,TimetableEntry.start_time)).all()
@router.post("/scheduling/overrides",response_model=OverrideRead)
def create_override(p:OverrideCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    if not db.get(TimetableEntry,p.timetable_entry_id):raise HTTPException(404,"Timetable entry not found")
    if p.new_teacher_id is not None and not db.get(Teacher,p.new_teacher_id):raise HTTPException(404,"Substitute teacher not found")
    if db.scalar(select(ScheduleOverride).where(ScheduleOverride.timetable_entry_id==p.timetable_entry_id,ScheduleOverride.override_date==p.override_date)):raise HTTPException(409,"An override already exists for this class and date")
    obj=create_schedule_override(db,**p.model_dump(),created_by=user.id);log_audit(db,user.id,"schedule_override.created","schedule_override",obj.id,None,p.model_dump());db.commit();db.refresh(obj);return obj
@router.get("/scheduling/overrides",response_model=list[OverrideRead])
def list_overrides(user:Annotated[User,Depends(require_role("admin"))],db:DbSession,date_from:date|None=None,date_to:date|None=None,status:str|None=None):
    q=select(ScheduleOverride)
    if date_from:q=q.where(ScheduleOverride.override_date>=date_from)
    if date_to:q=q.where(ScheduleOverride.override_date<=date_to)
    if status:q=q.where(ScheduleOverride.status==OverrideStatus(status))
    return db.scalars(q.order_by(ScheduleOverride.override_date.desc())).all()
@router.patch("/scheduling/overrides/{id}",response_model=OverrideRead)
def decide_override(id:int,p:OverrideDecision,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
    obj=db.get(ScheduleOverride,id)
    if not obj:raise HTTPException(404,"Override not found")
    before=obj.status.value
    try:obj.status=OverrideStatus(p.status)
    except ValueError as exc:raise HTTPException(422,"Status must be approved or rejected") from exc
    if obj.status==OverrideStatus.PENDING:raise HTTPException(422,"Choose approved or rejected")
    log_audit(db,user.id,"schedule_override.decision","schedule_override",obj.id,{"status":before},{"status":obj.status.value});db.commit();db.refresh(obj);return obj
@router.get("/teachers/me/current-sessions",response_model=list[CurrentSession])
def current_sessions(user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    teacher=teacher_profile(db,user);now=datetime.now();entries=db.scalars(select(TimetableEntry).where(TimetableEntry.day_of_week==now.weekday())).all();result=[]
    for entry in entries:
        override=approved_override(db,entry.id,now.date());effective_teacher=override.new_teacher_id if override and override.new_teacher_id else entry.teacher_id
        if effective_teacher!=teacher.id or (override and override.is_cancelled):continue
        start=override.start_time if override and override.start_time else entry.start_time;end=override.end_time if override and override.end_time else entry.end_time
        if start<=now.time()<=end:
            session=db.scalar(select(ClassSession).where(ClassSession.timetable_entry_id==entry.id,ClassSession.session_date==now.date()))
            result.append(CurrentSession(timetable_entry_id=entry.id,subject_name=entry.subject.name,original_teacher_id=entry.teacher_id,effective_teacher_id=effective_teacher,original_room=entry.room_name,room_name=override.new_room if override and override.new_room else entry.room_name,start_time=start,end_time=end,class_session_id=session.id if session else None,status=session.status.value if session else None,override_id=override.id if override else None))
    return result
@router.post("/sessions/{entry_id}/start",response_model=ClassSessionRead)
def start_session(entry_id:int,user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
    teacher=teacher_profile(db,user);entry=db.get(TimetableEntry,entry_id)
    if not entry:raise HTTPException(404,"Timetable entry not found")
    today=datetime.now().date();override=approved_override(db,entry_id,today);effective=override.new_teacher_id if override and override.new_teacher_id else entry.teacher_id
    if override and override.is_cancelled:raise HTTPException(409,"Class is cancelled")
    if effective!=teacher.id:raise HTTPException(403,"This session is assigned to another teacher")
    session=db.scalar(select(ClassSession).where(ClassSession.timetable_entry_id==entry_id,ClassSession.session_date==today))
    if not session:session=ClassSession(timetable_entry_id=entry_id,session_date=today,effective_teacher_id=effective,effective_room=override.new_room if override and override.new_room else entry.room_name,schedule_override_id=override.id if override else None,status=SessionStatus.ACTIVE,self_checkin_window_minutes=settings.attendance_self_checkin_window_minutes,challenge_rotation_seconds=settings.attendance_challenge_rotation_seconds);db.add(session);db.flush();log_audit(db,user.id,"class_session.started","class_session",session.id,None,{"timetable_entry_id":entry_id});db.commit();db.refresh(session)
    return session
@router.get("/sessions",response_model=list[SessionHistory])
def history(user:Annotated[User,Depends(require_roles("teacher","admin"))],db:DbSession,teacher_id:int|None=None,date_from:date|None=None,date_to:date|None=None):
    q=select(ClassSession)
    if user.role.value=="teacher":q=q.where(ClassSession.effective_teacher_id==teacher_profile(db,user).id)
    elif teacher_id:q=q.where(ClassSession.effective_teacher_id==teacher_id)
    if date_from:q=q.where(ClassSession.session_date>=date_from)
    if date_to:q=q.where(ClassSession.session_date<=date_to)
    result=[]
    for s in db.scalars(q.order_by(ClassSession.session_date.desc())).all():
        source=resolve_session_schedule(s);name=source.module.title if s.routine_entry_id else source.subject.name
        if s.routine_entry_id:
            effective=resolve_effective_class(db,source,s.session_date);section_names=sorted(db.scalars(select(Section.name).where(Section.id.in_(effective.section_ids))).all())
        else:section_names=[source.section.name]
        result.append(SessionHistory(id=s.id,session_date=s.session_date,subject_name=name,section_names=section_names,effective_teacher_id=s.effective_teacher_id,effective_room=s.effective_room,status=s.status.value,finalized_at=s.finalized_at))
    return result
