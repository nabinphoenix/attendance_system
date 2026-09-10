import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from app.modules.platform.models import College
from app.modules.academic.models import Program, Batch, Section, Block, Room, Student, Teacher, AcademicModule, ModuleOffering
from app.modules.operations.models import AuditLog

@pytest.fixture
def context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(College(id=2,name="Second College",slug="second",is_active=True))
        for name,role,college in [("root",UserRole.SUPER_ADMIN,None),("admin1",UserRole.ADMIN,1),("admin2",UserRole.ADMIN,2)]:
            db.add(User(name=name,email=f"{name}@example.com",password_hash=hash_password("Password123!"),role=role,college_id=college))
        db.add_all([Block(id=1,name="Block A",college_id=1),Block(id=2,name="Block A",college_id=2)])
        db.flush()
        db.add_all([Room(id=1,block_id=1,name="Room 1",room_type="lecture",capacity=30,college_id=1),Room(id=2,block_id=2,name="Room 1",room_type="lecture",capacity=30,college_id=2)])
        db.commit()
    def get_test_db():
        with factory() as db:
            db.info["college_id"]=-1
            yield db
    app.dependency_overrides[get_db]=get_test_db
    with TestClient(app) as client:
        def auth(name):
            response=client.post("/api/v1/auth/login",json={"email":f"{name}@example.com","password":"Password123!"})
            assert response.status_code==200,response.text
            return {"Authorization":"Bearer "+response.json()["access_token"]}
        headers={name:auth(name) for name in ("root","admin1","admin2")}
        yield client,headers,factory
    app.dependency_overrides.clear()
    engine.dispose()


def test_admin_scope_and_spoofed_college(context):
    client,h,factory=context
    for name,expected in (("admin1",1),("admin2",2)):
        r=client.get("/api/v1/academic/rooms",headers=h[name]);assert r.status_code==200,r.text
        assert [row["id"] for row in r.json()]==[expected]
    assert client.get("/api/v1/academic/rooms",headers=h["admin1"]|{"X-College-ID":"2"}).status_code==403
    assert client.patch("/api/v1/academic/rooms/2",headers=h["admin1"],json={"name":"Hacked"}).status_code==404
    assert client.delete("/api/v1/academic/rooms/2",headers=h["admin1"]).status_code==404
    assert client.post("/api/v1/academic/rooms",headers=h["admin1"],json={"block_id":2,"name":"Other","room_type":"lecture","capacity":10}).status_code==404
    assert client.get("/api/v1/platform/colleges",headers=h["admin1"]).status_code==403
    assert client.patch("/api/v1/users/2",headers=h["admin1"],json={"role":"super_admin"}).status_code==403


def test_super_admin_context_and_new_college(context):
    client,h,factory=context
    root=h["root"]
    assert client.get("/api/v1/academic/rooms",headers=root).status_code==400
    assert [x["id"] for x in client.get("/api/v1/academic/rooms",headers=root|{"X-College-ID":"2"}).json()]==[2]
    r=client.post("/api/v1/platform/colleges",headers=root,json={"name":"Third College","slug":"third"});assert r.status_code==201,r.text
    college_id=r.json()["id"]
    r=client.post("/api/v1/platform/users",headers=root,json={"college_id":college_id,"name":"Admin Three","email":"admin3@example.com","password":"Password123!","role":"admin"});assert r.status_code==201,r.text
    assert r.json()["college_id"]==college_id
    assert client.get("/api/v1/platform/overview",headers=root).json()["colleges"]==3
    r=client.delete(f"/api/v1/platform/colleges/{college_id}",headers=root);assert r.status_code==409,r.text
    r=client.post("/api/v1/platform/colleges",headers=root,json={"name":"Empty","slug":"empty"});assert r.status_code==201,r.text
    assert client.delete(f"/api/v1/platform/colleges/{r.json()['id']}",headers=root).status_code==204


def test_audit_and_inactive_college(context):
    client,h,factory=context
    r=client.patch("/api/v1/academic/rooms/2",headers=h["root"]|{"X-College-ID":"2"},json={"name":"Updated room"});assert r.status_code==200,r.text
    audits=client.get("/api/v1/platform/audit-logs?college_id=2",headers=h["root"]).json()["items"]
    assert any(a["entity_type"]=="rooms" and a["action"]=="record.updated" for a in audits)
    assert all(a["college_id"]==2 for a in audits)
    local=client.get("/api/v1/audit-logs",headers=h["admin1"])
    assert local.status_code==200,local.text
    assert all(a["entity_id"]!=2 or a["entity_type"]!="rooms" for a in local.json()["items"])
    assert client.patch("/api/v1/platform/colleges/2",headers=h["root"],json={"is_active":False}).status_code==200
    assert client.get("/api/v1/academic/rooms",headers=h["admin2"]).status_code==403
    assert client.post("/api/v1/auth/login",json={"email":"admin2@example.com","password":"Password123!"}).status_code==403
    assert client.get("/api/v1/academic/rooms",headers=h["root"]|{"X-College-ID":"2"}).status_code==200


def test_orm_aggregates_relationships_and_secondary_ownership(context):
    _,_,factory=context
    with factory() as db:
        db.info["college_id"]=2
        assert db.scalar(select(func.count()).select_from(Room))==1
        assert db.get(Room,1) is None
        room=db.get(Room,2);assert room.block.college_id==2
        program=Program(name="BSc",college_id=2);db.add(program);db.flush()
        batch=Batch(name="Batch",program_id=program.id,college_id=2);db.add(batch);db.flush()
        from app.modules.academic.models import Intake, ModuleOfferingSection
        from datetime import date
        intake=Intake(name="Intake",code="INT",program_id=program.id,start_date=date(2026,1,1),college_id=2)
        section=Section(name="A",batch_id=batch.id,college_id=2)
        module=AcademicModule(code="M",title="Module",credits=3,semester_number=1,college_id=2)
        db.add_all([intake,section,module]);db.flush()
        offering=ModuleOffering(academic_module_id=module.id,intake_id=intake.id,batch_id=batch.id,semester_number=1,college_id=2,sections=[section]);db.add(offering);db.commit()
        assert db.scalar(select(ModuleOfferingSection)).college_id==2
        room.block_id=1
        with pytest.raises(Exception,match="same college"):
            db.flush()
        db.rollback()


def test_account_profiles_and_configuration(context):
    client,h,factory=context
    root=h["root"]
    r=client.post("/api/v1/platform/users",headers=root,json={"college_id":2,"name":"Teacher","email":"teacher2@example.com","password":"Password123!","role":"teacher","employee_code":"T1"});assert r.status_code==201,r.text
    user_id=r.json()["id"]
    with factory() as db:
        assert db.scalar(select(Teacher).where(Teacher.user_id==user_id)).college_id==2
    assert client.post("/api/v1/platform/users",headers=root,json={"college_id":2,"name":"Student","email":"student2@example.com","password":"Password123!","role":"student","section_id":999,"roll_number":"R1"}).status_code==422
    r=client.put("/api/v1/platform/configuration",headers=root,json={"platform_name":"Platform","support_email":"help@example.com","allow_college_creation":False});assert r.status_code==200,r.text
    assert client.post("/api/v1/platform/colleges",headers=root,json={"name":"Blocked","slug":"blocked"}).status_code==403
    audit=client.get("/api/v1/platform/audit-logs",headers=root).text
    assert "Password123!" not in audit and "password_hash" not in audit
