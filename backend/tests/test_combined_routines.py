from datetime import date, time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, RoutineEntrySection, Section, Student, Teacher, TimeSlot
from app.modules.academic.routine_router import RoutineCreate, check_routine_conflicts, create_or_merge_routine_entry, create_routine_entry, routine_query, valid_routine
from app.modules.identity.models import User, UserRole


@pytest.mark.parametrize("class_type",["Lecture","Tutorial","Practical"])
def test_combined_routine_is_one_entry_and_visible_to_every_participant(class_type):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    with Session() as db:
        program=Program(name="IT");db.add(program);db.flush();intake=Intake(name="September",code="SEP",start_date=date(2026,9,1),program_id=program.id);db.add(intake);db.flush();batch=Batch(name="2026",program_id=program.id);db.add(batch);db.flush()
        a2=Section(name="A2",batch_id=batch.id,intake_id=intake.id,semester_number=6);a3=Section(name="A3",batch_id=batch.id,intake_id=intake.id,semester_number=6);a4=Section(name="A4",batch_id=batch.id,intake_id=intake.id,semester_number=6);db.add_all([a2,a3,a4]);block=Block(name="Block B");db.add(block);db.flush();room=Room(block_id=block.id,name="L04",room_type="lecture",capacity=60);module=AcademicModule(code="CT004",title="Advanced Database Systems",credits=3,semester_number=6);kind=ClassType(name=class_type);slot=TimeSlot(start_time=time(8,30),end_time=time(9,30),duration_label="1h");teacher_user=User(name="Karan",email="karan@example.com",password_hash="x",role=UserRole.TEACHER);db.add_all([room,module,kind,slot,teacher_user]);db.flush();offering=ModuleOffering(academic_module_id=module.id,intake_id=intake.id,batch_id=batch.id,semester_number=6,sections=[a2,a3,a4]);db.add(offering);teacher=Teacher(user_id=teacher_user.id,employee_code="T1");db.add(teacher);db.flush()
        payload=RoutineCreate(intake_id=intake.id,semester_number=6,section_id=a3.id,section_ids=[a3.id,a4.id],module_id=module.id,class_type_id=kind.id,teacher_id=teacher.id,room_id=room.id,day_of_week=6,time_slot_id=slot.id)
        first=payload.model_copy(update={"section_id":a3.id,"section_ids":[a3.id]})
        valid_routine(db,first);check_routine_conflicts(db,first);entry=create_routine_entry(db,first);db.commit()
        entry,state=create_or_merge_routine_entry(db,payload);db.commit();assert state=="merge"
        assert db.query(RoutineEntry).count()==1
        assert {x.section_id for x in db.query(RoutineEntrySection).all()}=={a3.id,a4.id}
        assert {x.id for x in db.scalars(routine_query().join(RoutineEntrySection).where(RoutineEntrySection.section_id==a3.id)).unique()}=={entry.id}
        assert {x.id for x in db.scalars(routine_query().join(RoutineEntrySection).where(RoutineEntrySection.section_id==a4.id)).unique()}=={entry.id}
        assert not db.scalars(routine_query().join(RoutineEntrySection).where(RoutineEntrySection.section_id==a2.id)).unique().all()
        _,state=create_or_merge_routine_entry(db,payload);assert state=="existing";assert db.query(RoutineEntry).count()==1
        collision=payload.model_copy(update={"section_id":a2.id,"section_ids":[a2.id]})
        try: check_routine_conflicts(db,collision);assert False,"teacher collision should be rejected"
        except Exception as exc: assert getattr(exc,"status_code",None)==409
