from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.academic.models import (
    AcademicModule,
    Batch,
    Block,
    ClassType,
    has_consistent_module_offering_context,
    Intake,
    ModuleOffering,
    ModuleOfferingSection,
    Program,
    Room,
    RoutineEntry,
    Section,
    Subject,
    Teacher,
    TimeSlot,
)
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import TimetableEntry


def test_module_offering_foundation_and_legacy_models_remain_separate():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        program = Program(name="IT")
        db.add(program)
        db.flush()
        intake = Intake(name="September", code="SEP", start_date=date(2026, 9, 1), program_id=program.id)
        batch = Batch(name="2026", program_id=program.id)
        module = AcademicModule(code="CT004", title="Databases", credits=3, semester_number=6)
        db.add_all([intake, batch, module])
        db.flush()
        section = Section(name="A1", batch_id=batch.id, intake_id=intake.id, semester_number=6)
        db.add(section)
        db.flush()

        offering = ModuleOffering(
            academic_module_id=module.id,
            intake_id=intake.id,
            batch_id=batch.id,
            semester_number=6,
        )
        offering.sections.append(section)
        db.add(offering)
        db.flush()
        assert has_consistent_module_offering_context(offering)
        assert offering.sections == [section]
        assert section.module_offerings == [offering]

        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(ModuleOffering(academic_module_id=module.id, intake_id=intake.id, batch_id=batch.id, semester_number=6))
            db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(ModuleOfferingSection(module_offering_id=offering.id, section_id=section.id))
            db.flush()

        block = Block(name="Block B")
        class_type = ClassType(name="Lecture")
        slot = TimeSlot(start_time=time(8, 30), end_time=time(9, 30), duration_label="1h")
        teacher_user = User(name="Karan", email="karan@example.com", password_hash="x", role=UserRole.TEACHER)
        db.add_all([block, class_type, slot, teacher_user])
        db.flush()
        room = Room(block_id=block.id, name="L04", room_type="lecture", capacity=60)
        teacher = Teacher(user_id=teacher_user.id, employee_code="T1")
        db.add_all([room, teacher])
        db.flush()
        routine = RoutineEntry(
            intake_id=intake.id, semester_number=6, section_id=section.id, module_id=module.id,
            module_offering_id=offering.id, class_type_id=class_type.id, teacher_id=teacher.id,
            room_id=room.id, day_of_week=1, time_slot_id=slot.id,
        )
        db.add(routine)
        db.flush()
        assert routine.module_offering is offering
        assert offering.routines == [routine]

        assert set(Subject.__table__.c.keys()) == {"id", "name", "code", "section_id"}
        assert "module_offering_id" not in TimetableEntry.__table__.c
