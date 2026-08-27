from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from app.core.dependencies import DbSession, get_current_user, require_role
from app.modules.identity.models import User
from app.modules.operations.service import log_audit
from app.modules.scheduling.models import OverrideStatus, ScheduleOverride
from app.modules.scheduling.service import EffectiveClass, create_schedule_override, resolve_effective_class, routine_override_conflicts, validate_routine_override_conflicts
from .models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, RoutineEntrySection, RoutinePendingSection, Section, Student, Teacher, TimeSlot
from .module_offering_service import resolve_active_module_offering, synchronize_offering_sections, validate_offering_context
from .student_profile_service import current_student_profile

router=APIRouter(prefix="/academic",tags=["routine"],dependencies=[Depends(require_role("admin"))])
student_router=APIRouter(prefix="/academic",tags=["routine"])
class ORM(BaseModel):model_config=ConfigDict(from_attributes=True)
class IntakeCreate(BaseModel):name:str;code:str;start_date:date;program_id:int
class IntakeUpdate(BaseModel):name:str|None=None;code:str|None=None;start_date:date|None=None;program_id:int|None=None
class IntakeRead(ORM):id:int;name:str;code:str;start_date:date;program_id:int
class BlockCreate(BaseModel):name:str
class BlockUpdate(BaseModel):name:str|None=None
class BlockRead(ORM):id:int;name:str
class RoomCreate(BaseModel):
 block_id:int;name:str;room_type:str;capacity:int
 latitude:float|None=Field(default=None,ge=-90,le=90);longitude:float|None=Field(default=None,ge=-180,le=180);geofence_radius_meters:float|None=Field(default=None,gt=0)
class RoomUpdate(BaseModel):
 block_id:int|None=None;name:str|None=None;room_type:str|None=None;capacity:int|None=None
 latitude:float|None=Field(default=None,ge=-90,le=90);longitude:float|None=Field(default=None,ge=-180,le=180);geofence_radius_meters:float|None=Field(default=None,gt=0)
class RoomRead(ORM):
 id:int;block_id:int;name:str;room_type:str;capacity:int;latitude:float|None;longitude:float|None;geofence_radius_meters:float|None
class ModuleCreate(BaseModel):code:str;title:str;credits:int;semester_number:int
class ModuleUpdate(BaseModel):code:str|None=None;title:str|None=None;credits:int|None=None;semester_number:int|None=None
class ModuleRead(ORM):id:int;code:str;title:str;credits:int;semester_number:int
class ModuleOfferingCreate(BaseModel):
 academic_module_id:int;intake_id:int;batch_id:int;semester_number:int;section_ids:list[int]=Field(default_factory=list,description="Deprecated: cohort sections are inherited automatically.");is_active:bool=True
class ModuleOfferingUpdate(BaseModel):
 academic_module_id:int|None=None;intake_id:int|None=None;batch_id:int|None=None;semester_number:int|None=None;section_ids:list[int]|None=Field(default=None,description="Deprecated: cohort sections are inherited automatically.");is_active:bool|None=None
class ModuleOfferingRead(BaseModel):
 id:int;academic_module_id:int;module_code:str;module_title:str;intake_id:int;intake_code:str;batch_id:int;batch_name:str;semester_number:int;section_ids:list[int];section_names:list[str];is_active:bool
class ClassTypeCreate(BaseModel):name:str
class ClassTypeUpdate(BaseModel):name:str|None=None
class ClassTypeRead(ORM):id:int;name:str
class TimeSlotCreate(BaseModel):start_time:time;end_time:time;duration_label:str
class TimeSlotUpdate(BaseModel):start_time:time|None=None;end_time:time|None=None;duration_label:str|None=None
class TimeSlotRead(ORM):id:int;start_time:time;end_time:time;duration_label:str
class RoutineCreate(BaseModel):
 intake_id:int;semester_number:int;section_id:int;module_id:int;class_type_id:int;teacher_id:int;room_id:int;day_of_week:int;time_slot_id:int
 section_ids:list[int]=[]
class RoutineUpdate(BaseModel):
 intake_id:int|None=None;semester_number:int|None=None;section_id:int|None=None;module_id:int|None=None;class_type_id:int|None=None;teacher_id:int|None=None;room_id:int|None=None;day_of_week:int|None=None;time_slot_id:int|None=None;section_ids:list[int]|None=None
class RoutineRead(ORM):
 id:int;intake_id:int;semester_number:int;section_id:int;module_id:int;module_offering_id:int;class_type_id:int;teacher_id:int;room_id:int;day_of_week:int;time_slot_id:int
 section_ids:list[int]=[]; section_names:list[str]=[]
class RoutinePage(BaseModel):
 items:list[RoutineRead];total:int;page:int;page_size:int
class RoutineConflict(BaseModel):
 resource:str;title:str;description:str;routine_id:int;class_label:str;teacher_name:str;room_name:str;section_names:list[str];time_range:str
class RoutineAvailability(BaseModel):
 available:bool;conflicts:list[RoutineConflict]=[]
class EffectiveRoutineRead(BaseModel):
 routine_id:int;date:date;start_time:time;end_time:time;teacher_id:int;original_teacher_id:int;room:str;original_room:str;section_ids:list[int];section_names:list[str];module_id:int;class_type_id:int;cancelled:bool;override_id:int|None;can_start:bool=False


@student_router.get("/catalog")
def routine_catalog(user:Annotated[User,Depends(get_current_user)],db:DbSession):
 """Read-only reference data needed to render student and teacher routines."""
 return {
  "modules":[{"id":item.id,"code":item.code,"title":item.title} for item in db.scalars(select(AcademicModule).order_by(AcademicModule.code)).all()],
  "class-types":[{"id":item.id,"name":item.name} for item in db.scalars(select(ClassType).order_by(ClassType.name)).all()],
  "rooms":[{"id":item.id,"block_id":item.block_id,"name":item.name} for item in db.scalars(select(Room).order_by(Room.name)).all()],
  "blocks":[{"id":item.id,"name":item.name} for item in db.scalars(select(Block).order_by(Block.name)).all()],
  "time-slots":[{"id":item.id,"start_time":item.start_time.isoformat(),"end_time":item.end_time.isoformat()} for item in db.scalars(select(TimeSlot).order_by(TimeSlot.start_time,TimeSlot.end_time)).all()],
  "intakes":[{"id":item.id,"name":item.name,"code":item.code} for item in db.scalars(select(Intake).order_by(Intake.start_date.desc())).all()],
  "teachers":[{"id":item.id,"name":item.user.name,"employee_code":item.employee_code} for item in db.scalars(select(Teacher).order_by(Teacher.employee_code)).all()],
 }

def save(db,obj,actor,action,entity):db.add(obj);db.flush();log_audit(db,actor.id,action,entity,obj.id,None,{});db.commit();db.refresh(obj);return obj
def modify(db,obj,values,actor,entity):
 for key,value in values.items():setattr(obj,key,value)
 db.flush();log_audit(db,actor.id,f"{entity}.updated",entity,obj.id,None,values);db.commit();db.refresh(obj);return obj
def remove(db,obj,actor,entity):
 ident=obj.id;db.delete(obj);log_audit(db,actor.id,f"{entity}.deleted",entity,ident,{"id":ident},None);db.commit()
def get(db,model,id,label):
 obj=db.get(model,id)
 if not obj:raise HTTPException(404,f"{label} not found")
 return obj
def routine_section_ids(entry:RoutineEntry)->set[int]:
 return {link.section_id for link in entry.section_links} or {entry.section_id}
def payload_section_ids(p:RoutineCreate)->set[int]:
 return set(p.section_ids or [p.section_id])
def routine_read(entry:RoutineEntry)->RoutineRead:
 links=entry.section_links
 ids=[link.section_id for link in links] or [entry.section_id]
 names=[link.section.name for link in links if link.section] or [entry.section.name]
 return RoutineRead(**{key:getattr(entry,key) for key in RoutineRead.model_fields if key not in {"section_ids","section_names"}},section_ids=ids,section_names=names)
def routine_query():
 return select(RoutineEntry).options(joinedload(RoutineEntry.section),joinedload(RoutineEntry.module),joinedload(RoutineEntry.class_type),joinedload(RoutineEntry.teacher).joinedload(Teacher.user),joinedload(RoutineEntry.room),joinedload(RoutineEntry.section_links).joinedload(RoutineEntrySection.section))
def matching_physical_routine(db,p:RoutineCreate)->RoutineEntry|None:
 """Find the one physical class, deliberately independent of its sections."""
 q=routine_query().where(
  RoutineEntry.intake_id==p.intake_id,RoutineEntry.semester_number==p.semester_number,
  RoutineEntry.day_of_week==p.day_of_week,RoutineEntry.time_slot_id==p.time_slot_id,
  RoutineEntry.teacher_id==p.teacher_id,RoutineEntry.module_id==p.module_id,
  RoutineEntry.class_type_id==p.class_type_id,RoutineEntry.room_id==p.room_id,
 )
 return db.scalars(q).unique().first()
def routine_conflicts(db,p:RoutineCreate,exclude_id:int|None=None)->list[RoutineConflict]:
 slot=db.get(TimeSlot,p.time_slot_id)
 if not slot: raise HTTPException(404,"Time slot not found")
 q=routine_query().join(TimeSlot,RoutineEntry.time_slot_id==TimeSlot.id).where(RoutineEntry.day_of_week==p.day_of_week,TimeSlot.start_time<slot.end_time,TimeSlot.end_time>slot.start_time)
 if exclude_id:q=q.where(RoutineEntry.id!=exclude_id)
 requested=payload_section_ids(p)
 day_label=("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")[p.day_of_week]
 conflicts=[]
 for entry in db.scalars(q).unique().all():
   names=" + ".join(link.section.name for link in entry.section_links) or entry.section.name
   existing_interval=f"{entry.time_slot.start_time:%H:%M} to {entry.time_slot.end_time:%H:%M}"
   class_label=f"{entry.module.code} - {entry.module.title} ({entry.class_type.name})"
   common={"routine_id":entry.id,"class_label":class_label,"teacher_name":entry.teacher.user.name,"room_name":entry.room.name,"section_names":names.split(" + "),"time_range":existing_interval}
   interval=f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"
   if entry.teacher_id==p.teacher_id:conflicts.append(RoutineConflict(resource="teacher",title="Teacher conflict",description=f"{entry.teacher.user.name} already teaches {class_label} for {names} in {entry.room.name} on {day_label}, {existing_interval}.",**common))
   if entry.room_id==p.room_id:conflicts.append(RoutineConflict(resource="room",title="Room conflict",description=f"{entry.room.name} is occupied by {entry.teacher.user.name}'s {class_label} class for {names} on {day_label}, {existing_interval}.",**common))
   overlap=requested & routine_section_ids(entry)
   if overlap:
    shared_names=" + ".join(db.get(Section,section_id).name for section_id in sorted(overlap))
    conflicts.append(RoutineConflict(resource="section",title="Section conflict",description=f"{shared_names} already has {class_label} with {entry.teacher.user.name} in {entry.room.name} on {day_label}, {existing_interval}.",**common))
 return conflicts
def check_routine_conflicts(db,p:RoutineCreate,exclude_id:int|None=None):
 conflicts=routine_conflicts(db,p,exclude_id)
 if conflicts:raise HTTPException(409,f"{conflicts[0].title}: {conflicts[0].description}")
def valid_routine(db,p:RoutineCreate):
 intake=get(db,Intake,p.intake_id,"Intake");section=get(db,Section,p.section_id,"Section");module=get(db,AcademicModule,p.module_id,"Module");get(db,ClassType,p.class_type_id,"Class type");get(db,Teacher,p.teacher_id,"Lecturer");get(db,Room,p.room_id,"Room");slot=get(db,TimeSlot,p.time_slot_id,"Time slot")
 if p.day_of_week not in range(7):raise HTTPException(422,"Day of week must be between 0 (Monday) and 6 (Sunday)")
 if slot.start_time>=slot.end_time:raise HTTPException(422,"Time slot end time must be after start time")
 sections=[]
 for section_id in payload_section_ids(p):
  section=get(db,Section,section_id,"Section");sections.append(section)
  if (section.intake_id is not None and section.intake_id!=intake.id) or (section.semester_number is not None and section.semester_number!=p.semester_number):raise HTTPException(422,"Section does not belong to the selected intake and semester")
 if module.semester_number!=p.semester_number:raise HTTPException(422,"Module does not belong to the selected semester")
 return resolve_active_module_offering(db,module=module,intake=intake,semester_number=p.semester_number,sections=sections)
@router.post("/intakes",response_model=IntakeRead)
def create_intake(p:IntakeCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return save(db,Intake(**p.model_dump()),user,"intake.created","intake")
@router.get("/intakes",response_model=list[IntakeRead])
def intakes(db:DbSession):return db.scalars(select(Intake).order_by(Intake.start_date.desc())).all()
@router.patch("/intakes/{id}",response_model=IntakeRead)
def update_intake(id:int,p:IntakeUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 values=p.model_dump(exclude_none=True)
 if "program_id" in values:get(db,Program,values["program_id"],"Program")
 return modify(db,get(db,Intake,id,"Intake"),values,user,"intake")
@router.delete("/intakes/{id}",status_code=204)
def delete_intake(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):remove(db,get(db,Intake,id,"Intake"),user,"intake")
@router.post("/blocks",response_model=BlockRead)
def create_block(p:BlockCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return save(db,Block(**p.model_dump()),user,"block.created","block")
@router.get("/blocks",response_model=list[BlockRead])
def blocks(db:DbSession):return db.scalars(select(Block).order_by(Block.name)).all()
@router.patch("/blocks/{id}",response_model=BlockRead)
def update_block(id:int,p:BlockUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return modify(db,get(db,Block,id,"Block"),p.model_dump(exclude_none=True),user,"block")
@router.delete("/blocks/{id}",status_code=204)
def delete_block(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 obj=get(db,Block,id,"Block")
 if db.scalar(select(Room.id).where(Room.block_id==id)):raise HTTPException(409,"Cannot delete a block with rooms")
 remove(db,obj,user,"block")
@router.post("/rooms",response_model=RoomRead)
def create_room(p:RoomCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):get(db,Block,p.block_id,"Block");return save(db,Room(**p.model_dump()),user,"room.created","room")
@router.get("/rooms",response_model=list[RoomRead])
def rooms(db:DbSession,block_id:int|None=None):q=select(Room);q=q.where(Room.block_id==block_id) if block_id else q;return db.scalars(q.order_by(Room.name)).all()
@router.patch("/rooms/{id}",response_model=RoomRead)
def update_room(id:int,p:RoomUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 values=p.model_dump(exclude_unset=True)
 if "block_id" in values:get(db,Block,values["block_id"],"Block")
 return modify(db,get(db,Room,id,"Room"),values,user,"room")
@router.delete("/rooms/{id}",status_code=204)
def delete_room(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 if db.scalar(select(RoutineEntry.id).where(RoutineEntry.room_id==id)):raise HTTPException(409,"Cannot delete a room used by routine entries")
 remove(db,get(db,Room,id,"Room"),user,"room")
@router.post("/modules",response_model=ModuleRead)
def create_module(p:ModuleCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return save(db,AcademicModule(**p.model_dump()),user,"module.created","module")
@router.get("/modules",response_model=list[ModuleRead])
def modules(db:DbSession,semester_number:int|None=None):q=select(AcademicModule);q=q.where(AcademicModule.semester_number==semester_number) if semester_number else q;return db.scalars(q.order_by(AcademicModule.code)).all()
@router.patch("/modules/{id}",response_model=ModuleRead)
def update_module(id:int,p:ModuleUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return modify(db,get(db,AcademicModule,id,"Module"),p.model_dump(exclude_none=True),user,"module")
@router.delete("/modules/{id}",status_code=204)
def delete_module(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 if db.scalar(select(RoutineEntry.id).where(RoutineEntry.module_id==id)):raise HTTPException(409,"Cannot delete a module used by routine entries")
 remove(db,get(db,AcademicModule,id,"Module"),user,"module")

def module_offering_query():
 return select(ModuleOffering).options(joinedload(ModuleOffering.academic_module),joinedload(ModuleOffering.intake),joinedload(ModuleOffering.batch),joinedload(ModuleOffering.sections))
def module_offering_read(offering:ModuleOffering)->ModuleOfferingRead:
 sections=sorted(offering.sections,key=lambda section:(section.name,section.id))
 return ModuleOfferingRead(id=offering.id,academic_module_id=offering.academic_module_id,module_code=offering.academic_module.code,module_title=offering.academic_module.title,intake_id=offering.intake_id,intake_code=offering.intake.code,batch_id=offering.batch_id,batch_name=offering.batch.name,semester_number=offering.semester_number,section_ids=[section.id for section in sections],section_names=[section.name for section in sections],is_active=offering.is_active)
def get_module_offering(db,id:int)->ModuleOffering:
 offering=db.scalar(module_offering_query().where(ModuleOffering.id==id))
 if not offering:raise HTTPException(404,"Module offering not found")
 return offering

@router.post("/module-offerings",response_model=ModuleOfferingRead)
def create_module_offering(p:ModuleOfferingCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 validate_offering_context(db,academic_module_id=p.academic_module_id,intake_id=p.intake_id,batch_id=p.batch_id,semester_number=p.semester_number,section_ids=set())
 if db.scalar(select(ModuleOffering.id).where(ModuleOffering.academic_module_id==p.academic_module_id,ModuleOffering.intake_id==p.intake_id,ModuleOffering.batch_id==p.batch_id,ModuleOffering.semester_number==p.semester_number)):
  raise HTTPException(409,"A module offering already exists for this module, intake, batch, and semester")
 offering=ModuleOffering(academic_module_id=p.academic_module_id,intake_id=p.intake_id,batch_id=p.batch_id,semester_number=p.semester_number,is_active=p.is_active)
 try:
  db.add(offering);db.flush();sections=synchronize_offering_sections(db,offering);after=p.model_dump(exclude={"section_ids"})|{"inherited_section_ids":[section.id for section in sections]};log_audit(db,user.id,"module_offering.created","module_offering",offering.id,None,after);db.commit()
 except IntegrityError:
  db.rollback();raise HTTPException(409,"A module offering already exists for this module, intake, batch, and semester")
 return module_offering_read(get_module_offering(db,offering.id))

@router.get("/module-offerings",response_model=list[ModuleOfferingRead])
def module_offerings(db:DbSession,academic_module_id:int|None=None,intake_id:int|None=None,batch_id:int|None=None,semester_number:int|None=None,section_id:int|None=None,is_active:bool|None=None):
 q=module_offering_query()
 if academic_module_id is not None:q=q.where(ModuleOffering.academic_module_id==academic_module_id)
 if intake_id is not None:q=q.where(ModuleOffering.intake_id==intake_id)
 if batch_id is not None:q=q.where(ModuleOffering.batch_id==batch_id)
 if semester_number is not None:q=q.where(ModuleOffering.semester_number==semester_number)
 if section_id is not None:q=q.join(ModuleOffering.sections).where(Section.id==section_id)
 if is_active is not None:q=q.where(ModuleOffering.is_active==is_active)
 return [module_offering_read(offering) for offering in db.scalars(q.order_by(ModuleOffering.id)).unique().all()]

@router.get("/module-offerings/{id}",response_model=ModuleOfferingRead)
def module_offering(id:int,db:DbSession):return module_offering_read(get_module_offering(db,id))

@router.patch("/module-offerings/{id}",response_model=ModuleOfferingRead)
def update_module_offering(id:int,p:ModuleOfferingUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 offering=get_module_offering(db,id);values=p.model_dump(exclude_none=True);values.pop("section_ids",None);identity={key for key in ("academic_module_id","intake_id","batch_id","semester_number") if key in values}
 if identity and db.scalar(select(RoutineEntry.id).where(RoutineEntry.module_offering_id==id)):
  changed=any(values[key]!=getattr(offering,key) for key in identity)
  if changed:raise HTTPException(409,"Cannot change a module offering context while routine entries are linked to it")
 module_id=values.get("academic_module_id",offering.academic_module_id);intake_id=values.get("intake_id",offering.intake_id);batch_id=values.get("batch_id",offering.batch_id);semester=values.get("semester_number",offering.semester_number)
 validate_offering_context(db,academic_module_id=module_id,intake_id=intake_id,batch_id=batch_id,semester_number=semester,section_ids=set())
 duplicate=db.scalar(select(ModuleOffering.id).where(ModuleOffering.academic_module_id==module_id,ModuleOffering.intake_id==intake_id,ModuleOffering.batch_id==batch_id,ModuleOffering.semester_number==semester,ModuleOffering.id!=id))
 if duplicate:raise HTTPException(409,"A module offering already exists for this module, intake, batch, and semester")
 for key in ("academic_module_id","intake_id","batch_id","semester_number","is_active"):
  if key in values:setattr(offering,key,values[key])
 try:
  db.flush();sections=synchronize_offering_sections(db,offering);after=values|{"inherited_section_ids":[section.id for section in sections]};log_audit(db,user.id,"module_offering.updated","module_offering",offering.id,None,after);db.commit()
 except IntegrityError:
  db.rollback();raise HTTPException(409,"A module offering already exists for this module, intake, batch, and semester")
 return module_offering_read(get_module_offering(db,id))

@router.patch("/module-offerings/{id}/activation",response_model=ModuleOfferingRead)
def set_module_offering_activation(id:int,is_active:bool,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 return update_module_offering(id,ModuleOfferingUpdate(is_active=is_active),user,db)

@router.delete("/module-offerings/{id}",status_code=204)
def delete_module_offering(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 offering=get_module_offering(db,id)
 if db.scalar(select(RoutineEntry.id).where(RoutineEntry.module_offering_id==id)):
  raise HTTPException(409,"Cannot delete a module offering with linked routine entries")
 db.delete(offering);log_audit(db,user.id,"module_offering.deleted","module_offering",id,{"id":id},None);db.commit()
@router.post("/class-types",response_model=ClassTypeRead)
def create_class_type(p:ClassTypeCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return save(db,ClassType(**p.model_dump()),user,"class_type.created","class_type")
@router.get("/class-types",response_model=list[ClassTypeRead])
def class_types(db:DbSession):return db.scalars(select(ClassType).order_by(ClassType.name)).all()
@router.patch("/class-types/{id}",response_model=ClassTypeRead)
def update_class_type(id:int,p:ClassTypeUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):return modify(db,get(db,ClassType,id,"Class type"),p.model_dump(exclude_none=True),user,"class_type")
@router.delete("/class-types/{id}",status_code=204)
def delete_class_type(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 if db.scalar(select(RoutineEntry.id).where(RoutineEntry.class_type_id==id)):raise HTTPException(409,"Cannot delete a class type used by routine entries")
 remove(db,get(db,ClassType,id,"Class type"),user,"class_type")
@router.post("/time-slots",response_model=TimeSlotRead)
def create_time_slot(p:TimeSlotCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 if p.start_time>=p.end_time:raise HTTPException(422,"End time must be after start time")
 return save(db,TimeSlot(**p.model_dump()),user,"time_slot.created","time_slot")
@router.get("/time-slots",response_model=list[TimeSlotRead])
def time_slots(db:DbSession):return db.scalars(select(TimeSlot).order_by(TimeSlot.start_time)).all()
@router.patch("/time-slots/{id}",response_model=TimeSlotRead)
def update_time_slot(id:int,p:TimeSlotUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 obj=get(db,TimeSlot,id,"Time slot");values=p.model_dump(exclude_none=True);start=values.get("start_time",obj.start_time);end=values.get("end_time",obj.end_time)
 if start>=end:raise HTTPException(422,"End time must be after start time")
 return modify(db,obj,values,user,"time_slot")
@router.delete("/time-slots/{id}",status_code=204)
def delete_time_slot(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 if db.scalar(select(RoutineEntry.id).where(RoutineEntry.time_slot_id==id)):raise HTTPException(409,"Cannot delete a time slot used by routine entries")
 remove(db,get(db,TimeSlot,id,"Time slot"),user,"time_slot")
def create_routine_entry(db,p:RoutineCreate):
 offering=valid_routine(db,p)
 entry=RoutineEntry(**p.model_dump(exclude={"section_ids"}),module_offering_id=offering.id)
 db.add(entry);db.flush()
 for section_id in payload_section_ids(p):db.add(RoutineEntrySection(routine_entry_id=entry.id,section_id=section_id))
 db.flush();return entry
def merge_routine_entry_sections(db,entry:RoutineEntry,p:RoutineCreate)->str:
 """Return new/existing/merge after checking only memberships not yet attached."""
 existing=routine_section_ids(entry); additions=payload_section_ids(p)-existing
 if not additions:return "existing"
 candidate=p.model_copy(update={"section_id":next(iter(additions)),"section_ids":list(additions)})
 offering=valid_routine(db,candidate)
 if entry.module_offering_id!=offering.id:raise HTTPException(422,"Combined class sections must resolve to the same module offering")
 check_routine_conflicts(db,candidate,entry.id)
 for section_id in additions:db.add(RoutineEntrySection(routine_entry_id=entry.id,section_id=section_id))
 db.flush();return "merge"

def persist_pending_section_references(db, entry: RoutineEntry, section_names: list[str], intake_id: int, semester_number: int) -> int:
    """Persist unresolved names and mark matching bridge memberships as resolved."""
    attached = {
        section.name.casefold(): section.id
        for section in db.scalars(
            select(Section).join(RoutineEntrySection).where(RoutineEntrySection.routine_entry_id == entry.id)
        )
    }
    pending = db.scalars(
        select(RoutinePendingSection).where(
            RoutinePendingSection.routine_entry_id == entry.id,
            RoutinePendingSection.resolved_section_id.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for item in pending:
        resolved_id = attached.get(item.section_name.casefold())
        if resolved_id is not None:
            item.resolved_section_id = resolved_id
            item.resolved_at = now
    existing = {item.section_name.casefold() for item in pending if item.resolved_section_id is None}
    created = 0
    for name in section_names:
        key = name.casefold()
        if key in attached or key in existing:
            continue
        db.add(
            RoutinePendingSection(
                routine_entry_id=entry.id,
                section_name=name.strip().upper(),
                intake_id=intake_id,
                semester_number=semester_number,
            )
        )
        existing.add(key)
        created += 1
    db.flush()
    return created
def create_or_merge_routine_entry(db,p:RoutineCreate)->tuple[RoutineEntry,str]:
 entry=matching_physical_routine(db,p)
 if entry:return entry,merge_routine_entry_sections(db,entry,p)
 valid_routine(db,p);check_routine_conflicts(db,p)
 return create_routine_entry(db,p),"new"
@router.post("/routines",response_model=RoutineRead)
def create_routine(p:RoutineCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 valid_routine(db,p);check_routine_conflicts(db,p);entry=create_routine_entry(db,p);log_audit(db,user.id,"routine.created","routine_entry",entry.id,None,p.model_dump());db.commit();return routine_read(db.scalar(routine_query().where(RoutineEntry.id==entry.id)))
@router.post("/routines/availability",response_model=RoutineAvailability)
def routine_availability(p:RoutineCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 valid_routine(db,p);conflicts=routine_conflicts(db,p)
 return RoutineAvailability(available=not conflicts,conflicts=conflicts)
def filtered_routine_query(intake_id:int|None=None,semester_number:int|None=None,section_id:int|None=None,teacher_id:int|None=None,module_id:int|None=None,day_of_week:int|None=None,room_id:int|None=None,block_id:int|None=None):
 q=routine_query()
 if intake_id:q=q.where(RoutineEntry.intake_id==intake_id)
 if semester_number:q=q.where(RoutineEntry.semester_number==semester_number)
 if section_id:q=q.outerjoin(RoutineEntrySection).where((RoutineEntry.section_id==section_id)|(RoutineEntrySection.section_id==section_id)).distinct()
 if teacher_id:q=q.where(RoutineEntry.teacher_id==teacher_id)
 if module_id:q=q.where(RoutineEntry.module_id==module_id)
 if day_of_week is not None:q=q.where(RoutineEntry.day_of_week==day_of_week)
 if room_id:q=q.where(RoutineEntry.room_id==room_id)
 if block_id:q=q.join(Room,RoutineEntry.room_id==Room.id).where(Room.block_id==block_id)
 return q
@router.get("/routines",response_model=list[RoutineRead])
def routines(db:DbSession,intake_id:int|None=None,semester_number:int|None=None,section_id:int|None=None,teacher_id:int|None=None,module_id:int|None=None,day_of_week:int|None=None,room_id:int|None=None,block_id:int|None=None):
 q=filtered_routine_query(intake_id,semester_number,section_id,teacher_id,module_id,day_of_week,room_id,block_id)
 return [routine_read(x) for x in db.scalars(q.join(TimeSlot,RoutineEntry.time_slot_id==TimeSlot.id).order_by(RoutineEntry.day_of_week,TimeSlot.start_time,RoutineEntry.id)).unique().all()]
@router.get("/routines/page",response_model=RoutinePage)
def routine_page(db:DbSession,page:int=Query(1,ge=1),page_size:int=Query(10,ge=5,le=100),intake_id:int|None=None,semester_number:int|None=None,section_id:int|None=None,teacher_id:int|None=None,module_id:int|None=None,day_of_week:int|None=None,room_id:int|None=None,block_id:int|None=None):
 q=filtered_routine_query(intake_id,semester_number,section_id,teacher_id,module_id,day_of_week,room_id,block_id)
 total=db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
 entries=db.scalars(q.join(TimeSlot,RoutineEntry.time_slot_id==TimeSlot.id).order_by(RoutineEntry.day_of_week,TimeSlot.start_time,RoutineEntry.id).offset((page-1)*page_size).limit(page_size)).unique().all()
 return RoutinePage(items=[routine_read(entry) for entry in entries],total=total,page=page,page_size=page_size)
@router.patch("/routines/{id}",response_model=RoutineRead)
def update_routine(id:int,p:RoutineUpdate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 obj=db.scalar(routine_query().where(RoutineEntry.id==id))
 if not obj:raise HTTPException(404,"Routine entry not found")
 values=p.model_dump(exclude_none=True);current={key:getattr(obj,key) for key in RoutineCreate.model_fields if key!="section_ids"};current["section_ids"]=list(routine_section_ids(obj));candidate=RoutineCreate(**(current|values));offering=valid_routine(db,candidate);check_routine_conflicts(db,candidate,id)
 for key,value in values.items():
  if key!="section_ids":setattr(obj,key,value)
 obj.module_offering_id=offering.id
 if "section_ids" in values:
  obj.section_id=next(iter(payload_section_ids(candidate)));obj.section_links.clear();db.flush()
  for section_id in payload_section_ids(candidate):db.add(RoutineEntrySection(routine_entry_id=obj.id,section_id=section_id))
 db.flush();log_audit(db,user.id,"routine_entry.updated","routine_entry",obj.id,None,values);db.commit();return routine_read(db.scalar(routine_query().where(RoutineEntry.id==id)))
@router.delete("/routines/{id}",status_code=204)
def delete_routine(id:int,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):remove(db,get(db,RoutineEntry,id,"Routine entry"),user,"routine_entry")
@student_router.get("/routines/me",response_model=list[RoutineRead])
def my_routine(user:Annotated[User,Depends(get_current_user)],db:DbSession):
 student=current_student_profile(db,user)
 section=student.section
 if not section.intake_id or not section.semester_number:return []
 q=routine_query().outerjoin(RoutineEntrySection).where((RoutineEntry.section_id==section.id)|(RoutineEntrySection.section_id==section.id)).order_by(RoutineEntry.day_of_week)
 return [routine_read(entry) for entry in db.scalars(q).unique().all()]

@student_router.get("/routines/me/today",response_model=list[RoutineRead])
def my_routine_today(user:Annotated[User,Depends(get_current_user)],db:DbSession):
 return [entry for entry in my_routine(user,db) if entry.day_of_week==datetime.now().weekday()]

@student_router.get("/teachers/me/routines",response_model=list[RoutineRead])
def my_teacher_routine(user:Annotated[User,Depends(require_role("teacher"))],db:DbSession):
 teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
 if not teacher:raise HTTPException(404,"Teacher profile not found")
 return routines(db,teacher_id=teacher.id)

@router.get("/teachers/{teacher_id}/routines",response_model=list[RoutineRead])
def teacher_routine(teacher_id:int,db:DbSession):
 get(db,Teacher,teacher_id,"Teacher")
 return routines(db,teacher_id=teacher_id)
class RoutineOverrideCreate(BaseModel):override_date:date;new_teacher_id:int|None=None;new_room:str|None=None;start_time:time|None=None;end_time:time|None=None;is_cancelled:bool=False;reason:str
class RoutineOverrideDecision(BaseModel):status:str
@router.get("/routines/{routine_id}/overrides")
def routine_overrides(routine_id:int,db:DbSession):return db.scalars(select(ScheduleOverride).where(ScheduleOverride.routine_entry_id==routine_id).order_by(ScheduleOverride.override_date.desc())).all()
@router.post("/routines/{routine_id}/overrides/availability",response_model=RoutineAvailability)
def routine_override_availability(routine_id:int,p:RoutineOverrideCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 entry=get(db,RoutineEntry,routine_id,"Routine entry")
 existing=db.scalar(select(ScheduleOverride).where(ScheduleOverride.routine_entry_id==routine_id,ScheduleOverride.override_date==p.override_date))
 if existing:
  section_names=[item.name for item in db.scalars(select(Section).join(RoutineEntrySection).where(RoutineEntrySection.routine_entry_id==entry.id)).all()] or [entry.section.name]
  conflict=RoutineConflict(resource="override",title="Override already exists",description=f"{entry.module.code} - {entry.module.title} already has a {existing.status.value} override for {p.override_date}. Review the override history instead of creating another one.",routine_id=entry.id,class_label=f"{entry.module.code} - {entry.module.title} ({entry.class_type.name})",teacher_name=entry.teacher.user.name,room_name=entry.room.name,section_names=section_names,time_range=f"{entry.time_slot.start_time:%H:%M} to {entry.time_slot.end_time:%H:%M}")
  return RoutineAvailability(available=False,conflicts=[conflict])
 if p.new_teacher_id is not None:get(db,Teacher,p.new_teacher_id,"Substitute teacher")
 proposed=ScheduleOverride(routine_entry_id=routine_id,created_by=user.id,status=OverrideStatus.PENDING,**p.model_dump())
 _,conflicts=routine_override_conflicts(db,entry,proposed)
 return RoutineAvailability(available=not conflicts,conflicts=[RoutineConflict(**item) for item in conflicts])
@router.post("/routines/{routine_id}/overrides")
def create_routine_override(routine_id:int,p:RoutineOverrideCreate,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 entry=get(db,RoutineEntry,routine_id,"Routine entry")
 if p.new_teacher_id is not None:get(db,Teacher,p.new_teacher_id,"Substitute teacher")
 if db.scalar(select(ScheduleOverride).where(ScheduleOverride.routine_entry_id==routine_id,ScheduleOverride.override_date==p.override_date)):raise HTTPException(409,"An override already exists for this routine and date")
 proposed=ScheduleOverride(routine_entry_id=routine_id,created_by=user.id,status=OverrideStatus.PENDING,**p.model_dump())
 validate_routine_override_conflicts(db,entry,proposed)
 obj=create_schedule_override(db,routine_entry_id=routine_id,created_by=user.id,**p.model_dump());log_audit(db,user.id,"routine_override.created","schedule_override",obj.id,None,{"routine_entry_id":routine_id,**p.model_dump()});db.commit();db.refresh(obj);return obj

@router.patch("/routines/{routine_id}/overrides/{override_id}")
def decide_routine_override(routine_id:int,override_id:int,p:RoutineOverrideDecision,user:Annotated[User,Depends(require_role("admin"))],db:DbSession):
 entry=get(db,RoutineEntry,routine_id,"Routine entry");override=db.get(ScheduleOverride,override_id)
 if not override or override.routine_entry_id!=routine_id:raise HTTPException(404,"Routine override not found")
 try:status=OverrideStatus(p.status)
 except ValueError as exc:raise HTTPException(422,"Status must be approved or rejected") from exc
 if status==OverrideStatus.PENDING:raise HTTPException(422,"Choose approved or rejected")
 if status==OverrideStatus.APPROVED:validate_routine_override_conflicts(db,entry,override)
 before=override.status.value;override.status=status;log_audit(db,user.id,"routine_override.decision","schedule_override",override.id,{"status":before},{"status":status.value});db.commit();db.refresh(override);return override

def effective_routine_read(db,effective:EffectiveClass)->EffectiveRoutineRead:
 entry=effective.routine_entry;sections=[db.get(Section,section_id) for section_id in sorted(effective.section_ids)]
 return EffectiveRoutineRead(routine_id=entry.id,date=effective.date,start_time=effective.start_time,end_time=effective.end_time,teacher_id=effective.teacher_id,original_teacher_id=entry.teacher_id,room=effective.room,original_room=entry.room.name,section_ids=list(sorted(effective.section_ids)),section_names=[section.name for section in sections if section],module_id=entry.module_id,class_type_id=entry.class_type_id,cancelled=effective.cancelled,override_id=effective.override_id)
def effective_occurrences(db,entries:list[RoutineEntry],date_from:date,days:int)->list[EffectiveRoutineRead]:
 result=[]
 for offset in range(min(max(days,1),31)):
  on_date=date_from+timedelta(days=offset)
  for entry in entries:
   if entry.day_of_week==on_date.weekday():result.append(effective_routine_read(db,resolve_effective_class(db,entry,on_date)))
  end_date=date_from+timedelta(days=min(max(days,1),31)-1)
  entry_by_id={entry.id:entry for entry in entries}
  makeup_overrides=db.scalars(select(ScheduleOverride).where(ScheduleOverride.routine_entry_id.in_(entry_by_id),ScheduleOverride.is_makeup.is_(True),ScheduleOverride.status==OverrideStatus.APPROVED,ScheduleOverride.override_date.between(date_from,end_date))).all()
  existing={(item.routine_id,item.date) for item in result}
  for override in makeup_overrides:
   key=(override.routine_entry_id,override.override_date)
   if key not in existing:result.append(effective_routine_read(db,resolve_effective_class(db,entry_by_id[override.routine_entry_id],override.override_date,override)))
 return sorted(result,key=lambda item:(item.date,item.start_time,item.routine_id))

@student_router.get("/routines/me/occurrences",response_model=list[EffectiveRoutineRead])
def my_routine_occurrences(user:Annotated[User,Depends(get_current_user)],db:DbSession,date_from:date,days:int=8):
 student=current_student_profile(db,user)
 entries=db.scalars(routine_query().outerjoin(RoutineEntrySection).where((RoutineEntry.section_id==student.section_id)|(RoutineEntrySection.section_id==student.section_id))).unique().all()
 return effective_occurrences(db,entries,date_from,days)

@student_router.get("/teachers/me/occurrences",response_model=list[EffectiveRoutineRead])
def my_teacher_occurrences(user:Annotated[User,Depends(require_role("teacher"))],db:DbSession,date_from:date,days:int=8):
 teacher=db.scalar(select(Teacher).where(Teacher.user_id==user.id))
 if not teacher:raise HTTPException(404,"Teacher profile not found")
 all_entries=db.scalars(routine_query()).unique().all();result=effective_occurrences(db,all_entries,date_from,days)
 return [item.model_copy(update={"can_start":item.teacher_id==teacher.id and not item.cancelled}) for item in result if item.original_teacher_id==teacher.id or item.teacher_id==teacher.id]

@router.get("/routine-occurrences",response_model=list[EffectiveRoutineRead])
def admin_routine_occurrences(db:DbSession,date_from:date,days:int=8):return effective_occurrences(db,db.scalars(routine_query()).unique().all(),date_from,days)
