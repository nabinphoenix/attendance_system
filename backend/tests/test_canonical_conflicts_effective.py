import io
from datetime import date, datetime, time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import AcademicModule, Batch, Block, ClassType, Intake, ModuleOffering, Program, Room, RoutineEntry, Section, Student, Teacher, TimeSlot
from app.modules.academic.routine_router import RoutineCreate, check_routine_conflicts, create_routine_entry
from app.modules.identity.models import User, UserRole
from app.modules.scheduling.models import ClassSession, OverrideStatus, ScheduleOverride
from app.modules.scheduling.service import resolve_effective_class, validate_routine_override_conflicts


def setup_context():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    def override_db():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override_db
    with Session() as db:
        program=Program(name="IT");db.add(program);db.flush();intake=Intake(name="September",code="SEP",start_date=date(2026,9,1),program_id=program.id);batch=Batch(name="2026",program_id=program.id);db.add_all([intake,batch]);db.flush()
        sections={name:Section(name=name,batch_id=batch.id,intake_id=intake.id,semester_number=6) for name in ("A1","A2","A3","A4")};module=AcademicModule(code="CT004",title="Advanced Database Systems",credits=3,semester_number=6);block=Block(name="Block B");db.add_all([*sections.values(),module,block]);db.flush()
        rooms={name:Room(block_id=block.id,name=name,room_type="lecture",capacity=60) for name in ("Annapurna","Khaptad-LT05","Codespace")};kinds={name:ClassType(name=name) for name in ("Lecture","Tutorial","Practical")};slots={label:TimeSlot(start_time=start,end_time=end,duration_label=label) for label,start,end in (("base",time(8),time(9)),("overlap",time(8,30),time(9,30)),("adjacent",time(9),time(10)),("later",time(12),time(13)))}
        users={name:User(name=name,email=f"{name.lower()}@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER) for name in ("Karan","Bina","Chandra")};admin=User(name="Admin",email="admin@example.com",password_hash=hash_password("Password123!"),role=UserRole.ADMIN);students={name:User(name=f"Student {name}",email=f"student-{name.lower()}@example.com",password_hash=hash_password("Password123!"),role=UserRole.STUDENT) for name in ("A1","A2","A3","A4")}
        db.add_all([*rooms.values(),*kinds.values(),*slots.values(),*users.values(),admin,*students.values()]);db.flush();offering=ModuleOffering(academic_module_id=module.id,intake_id=intake.id,batch_id=batch.id,semester_number=6,sections=list(sections.values()));teachers={name:Teacher(user_id=user.id,employee_code=f"T-{name}") for name,user in users.items()};db.add_all([offering,*teachers.values()]);db.flush();db.add_all([Student(user_id=students[name].id,section_id=sections[name].id,roll_number=f"R-{name}") for name in students]);db.flush()
        today=datetime.now().weekday();base=RoutineCreate(intake_id=intake.id,semester_number=6,section_id=sections["A1"].id,section_ids=[sections["A1"].id],module_id=module.id,class_type_id=kinds["Lecture"].id,teacher_id=teachers["Karan"].id,room_id=rooms["Annapurna"].id,day_of_week=today,time_slot_id=slots["base"].id);base_entry=create_routine_entry(db,base);db.commit()
        ids={"intake":intake.id,"module":module.id,"offering":offering.id,"base":base_entry.id,"today":today,"block":block.id,**{f"section_{k}":v.id for k,v in sections.items()},**{f"room_{k}":v.id for k,v in rooms.items()},**{f"kind_{k}":v.id for k,v in kinds.items()},**{f"slot_{k}":v.id for k,v in slots.items()},**{f"teacher_{k}":v.id for k,v in teachers.items()}}
    return Session,ids


def payload(ids,*,section="A3",sections=None,teacher="Bina",room="Khaptad-LT05",slot="overlap",kind="Lecture"):
    section_names=sections or [section]
    return {"intake_id":ids["intake"],"semester_number":6,"section_id":ids[f"section_{section_names[0]}"],"section_ids":[ids[f"section_{name}"] for name in section_names],"module_id":ids["module"],"class_type_id":ids[f"kind_{kind}"],"teacher_id":ids[f"teacher_{teacher}"],"room_id":ids[f"room_{room}"],"day_of_week":ids["today"],"time_slot_id":ids[f"slot_{slot}"]}


def auth(client,email):
    response=client.post("/api/v1/auth/login",json={"email":email,"password":"Password123!"});assert response.status_code==200,response.text;return {"Authorization":f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("kind",["Lecture","Tutorial","Practical"])
def test_builder_interval_conflicts_are_class_type_independent(kind):
    Session,ids=setup_context()
    with Session() as db:
        with pytest.raises(HTTPException,match="Room conflict") as exact:check_routine_conflicts(db,RoutineCreate(**payload(ids,slot="base",room="Annapurna",kind=kind)))
        assert exact.value.status_code==409
        with pytest.raises(HTTPException,match="Room conflict"):check_routine_conflicts(db,RoutineCreate(**payload(ids,room="Annapurna",kind=kind)))
        check_routine_conflicts(db,RoutineCreate(**payload(ids,slot="adjacent",room="Annapurna",kind=kind)))
        with pytest.raises(HTTPException,match="Teacher conflict"):check_routine_conflicts(db,RoutineCreate(**payload(ids,teacher="Karan",kind=kind)))
        with pytest.raises(HTTPException,match="Section conflict"):check_routine_conflicts(db,RoutineCreate(**payload(ids,section="A1",kind=kind)))
        with pytest.raises(HTTPException,match="Section conflict"):check_routine_conflicts(db,RoutineCreate(**payload(ids,sections=["A1","A2"],kind=kind)))
    app.dependency_overrides.clear()


def test_effective_override_conflicts_cancellation_and_start_session():
    Session,ids=setup_context();client=TestClient(app);admin=auth(client,"admin@example.com");karan=auth(client,"karan@example.com");bina=auth(client,"bina@example.com");chandra=auth(client,"chandra@example.com");today=date.today()
    with Session() as db:
        second=create_routine_entry(db,RoutineCreate(**payload(ids)));later=create_routine_entry(db,RoutineCreate(**payload(ids,section="A4",teacher="Karan",room="Codespace",slot="later",kind="Practical")));db.commit();second_id=second.id;later_id=later.id
        room_conflict=ScheduleOverride(routine_entry_id=second_id,override_date=today,new_room="Annapurna",reason="room",created_by=1,status=OverrideStatus.PENDING)
        with pytest.raises(HTTPException,match="Room conflict"):validate_routine_override_conflicts(db,second,room_conflict)
        substitute_conflict=ScheduleOverride(routine_entry_id=second_id,override_date=today,new_teacher_id=ids["teacher_Karan"],reason="sub",created_by=1,status=OverrideStatus.PENDING)
        with pytest.raises(HTTPException,match="Teacher conflict"):validate_routine_override_conflicts(db,second,substitute_conflict)
    room_response=client.post(f"/api/v1/academic/routines/{second_id}/overrides",headers=admin,json={"override_date":today.isoformat(),"new_room":"Annapurna","reason":"room conflict"});assert room_response.status_code==409 and "Room conflict" in room_response.json()["detail"]
    substitute_response=client.post(f"/api/v1/academic/routines/{second_id}/overrides",headers=admin,json={"override_date":today.isoformat(),"new_teacher_id":ids["teacher_Karan"],"reason":"teacher conflict"});assert substitute_response.status_code==409 and "Teacher conflict" in substitute_response.json()["detail"]
    with Session() as db:
        second=db.get(RoutineEntry,second_id);later=db.get(RoutineEntry,later_id)
        cancellation=ScheduleOverride(routine_entry_id=ids["base"],override_date=today,is_cancelled=True,reason="cancelled",created_by=1,status=OverrideStatus.APPROVED);db.add(cancellation);db.flush()
        validate_routine_override_conflicts(db,second,room_conflict)
        room_change=ScheduleOverride(routine_entry_id=second_id,override_date=today,new_room="Annapurna",reason="moved",created_by=1,status=OverrideStatus.APPROVED);db.add(room_change)
        substitute=ScheduleOverride(routine_entry_id=later_id,override_date=today,new_teacher_id=ids["teacher_Chandra"],reason="cover",created_by=1,status=OverrideStatus.APPROVED);db.add(substitute);db.commit()
        assert resolve_effective_class(db,second,today).room=="Annapurna"
        assert resolve_effective_class(db,later,today).teacher_id==ids["teacher_Chandra"]
    location={"latitude":27.7172,"longitude":85.3240,"accuracy_meters":12}
    assert client.post(f"/api/v1/routine-sessions/{ids['base']}/start",headers=karan,json=location).status_code==409
    assert client.post(f"/api/v1/routine-sessions/{later_id}/start",headers=karan,json=location).status_code==403
    started=client.post(f"/api/v1/routine-sessions/{later_id}/start",headers=chandra,json=location);assert started.status_code==200,started.text
    room_session=client.post(f"/api/v1/routine-sessions/{second_id}/start",headers=bina,json=location);assert room_session.status_code==200,room_session.text
    with Session() as db:
        assert db.get(ClassSession,started.json()["id"]).effective_teacher_id==ids["teacher_Chandra"]
        assert db.get(ClassSession,room_session.json()["id"]).effective_room=="Annapurna"
    date_query=f"date_from={today.isoformat()}&days=1"
    a1_occurrences=client.get(f"/api/v1/academic/routines/me/occurrences?{date_query}",headers=auth(client,"student-a1@example.com"));assert a1_occurrences.status_code==200 and a1_occurrences.json()[0]["cancelled"] is True
    a3_occurrences=client.get(f"/api/v1/academic/routines/me/occurrences?{date_query}",headers=auth(client,"student-a3@example.com"));assert a3_occurrences.status_code==200 and a3_occurrences.json()[0]["room"]=="Annapurna"
    teacher_occurrences=client.get(f"/api/v1/academic/teachers/me/occurrences?{date_query}",headers=chandra);assert teacher_occurrences.status_code==200 and any(row["routine_id"]==later_id and row["can_start"] for row in teacher_occurrences.json())
    admin_occurrences=client.get(f"/api/v1/academic/routine-occurrences?{date_query}",headers=admin);assert admin_occurrences.status_code==200 and any(row["cancelled"] for row in admin_occurrences.json());assert any(row["occupancy_status"]=="empty" for row in admin_occurrences.json());assert any(row["occupancy_status"]=="occupied" for row in admin_occurrences.json());assert any(row["routine_id"]==second_id and row["override_id"] and row["occupancy_status"]=="occupied" for row in admin_occurrences.json())
    app.dependency_overrides.clear()


def test_combined_visibility_and_import_preview_conflicts():
    Session,ids=setup_context();client=TestClient(app);admin=auth(client,"admin@example.com")
    with Session() as db:
        combined=create_routine_entry(db,RoutineCreate(**payload(ids,sections=["A3","A4"],teacher="Karan",room="Codespace",slot="later",kind="Tutorial")));db.commit();combined_id=combined.id
    for section,expected in (("A3",1),("A4",1),("A2",0)):
        rows=client.get("/api/v1/academic/routines/me",headers=auth(client,f"student-{section.lower()}@example.com")).json();assert len(rows)==expected
        if rows:assert rows[0]["id"]==combined_id and set(rows[0]["section_names"])=={"A3","A4"}
    teacher_rows=client.get("/api/v1/academic/teachers/me/routines",headers=auth(client,"karan@example.com")).json();assert sum(row["id"]==combined_id for row in teacher_rows)==1
    admin_rows=client.get(f"/api/v1/academic/routines?section_id={ids['section_A3']}",headers=admin).json();assert sum(row["id"]==combined_id for row in admin_rows)==1
    day=["MON","TUE","WED","THU","FRI","SAT","SUN"][ids["today"]]
    teacher_csv=f"intake_code,semester,sections,day,start_time,end_time,module_code,class_type,block,room\nSEP,SEM VI,A3,{day},08:30,09:30,CT004,Lecture,Block B,Annapurna\n".encode()
    preview=client.post(f"/api/v1/academic/teachers/{ids['teacher_Chandra']}/timetable/preview",headers=admin,files={"file":("conflict.csv",io.BytesIO(teacher_csv),"text/csv")});assert preview.status_code==200 and preview.json()["invalid_rows"]==1;assert "Room conflict" in preview.json()["errors"][0]["error_message"]
    section_csv=f"day,start_time,end_time,sections,module_code,module_title,class_type,lecturer_email,block,room\n{day},08:30,09:30,A3,CT004,Advanced Database Systems,Lecture,chandra@example.com,Block B,Annapurna\n".encode()
    section_preview=client.post(f"/api/v1/academic/sections/{ids['section_A3']}/routine/preview?intake_id={ids['intake']}&semester_number=6",headers=admin,files={"file":("conflict.csv",io.BytesIO(section_csv),"text/csv")});assert section_preview.status_code==200 and section_preview.json()["invalid_rows"]==1;assert "Room conflict" in section_preview.json()["errors"][0]["error_message"]
    app.dependency_overrides.clear()


def test_room_availability_groups_each_block_and_uses_room_ids_for_overrides():
    Session, ids = setup_context()
    client = TestClient(app)
    admin = auth(client, "admin@example.com")
    with Session() as db:
        block_c = Block(name="Block C")
        db.add(block_c)
        db.flush()
        duplicate_name_room = Room(block_id=block_c.id, name="Annapurna", room_type="lecture", capacity=40)
        db.add(duplicate_name_room)
        second = create_routine_entry(db, RoutineCreate(**payload(ids)))
        db.commit()

        candidate = ScheduleOverride(
            routine_entry_id=second.id,
            override_date=date.today(),
            new_room_id=duplicate_name_room.id,
            reason="Move to Block C",
            created_by=1,
            status=OverrideStatus.PENDING,
        )
        effective = validate_routine_override_conflicts(db, second, candidate)
        assert effective.room_id == duplicate_name_room.id

    response = client.get(f"/api/v1/academic/room-availability?day_of_week={ids['today']}", headers=admin)
    assert response.status_code == 200, response.text
    blocks = {block["name"]: block for block in response.json()["blocks"]}
    assert {"Block B", "Block C"}.issubset(blocks)
    block_b_room = next(room for room in blocks["Block B"]["rooms"] if room["id"] == ids["room_Annapurna"])
    base_slot = next(slot for slot in block_b_room["slots"] if slot["time_slot_id"] == ids["slot_base"])
    assert base_slot["status"] == "occupied" and base_slot["routine_id"] == ids["base"]
    assert all(slot["status"] == "available" for slot in blocks["Block C"]["rooms"][0]["slots"])
    app.dependency_overrides.clear()
