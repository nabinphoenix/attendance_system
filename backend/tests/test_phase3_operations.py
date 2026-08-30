import hashlib, io
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base,get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch,InvitationPurpose,InvitationStatus,Program,Section,Student,StudentInvitation,Subject,Teacher
from app.modules.identity.models import User,UserRole
from app.modules.operations.models import Notification
from app.modules.scheduling.models import ScheduleOverride,TimetableEntry

def setup_db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override
    with Session() as db:
        p=Program(name="BCA");db.add(p);db.flush();b=Batch(name="2026",program_id=p.id);db.add(b);db.flush();s=Section(name="A",batch_id=b.id);db.add(s);db.flush();subject=Subject(name="Architecture",code="ARC",section_id=s.id);db.add(subject);db.flush()
        admin=User(name="Admin",email="admin@example.com",password_hash=hash_password("Password123!"),role=UserRole.ADMIN);original=User(name="Original",email="original@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER);sub=User(name="Sub",email="sub@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER);db.add_all([admin,original,sub]);db.flush();ot=Teacher(user_id=original.id,employee_code="O");st=Teacher(user_id=sub.id,employee_code="S");db.add_all([ot,st]);db.flush();now=datetime.now();entry=TimetableEntry(teacher_id=ot.id,subject_id=subject.id,section_id=s.id,day_of_week=now.weekday(),start_time=now.time().replace(hour=max(now.hour-1,0)),end_time=now.time().replace(hour=min(now.hour+1,23)),room_name="R1",latitude=0,longitude=0);db.add(entry);db.commit();return Session,entry.id,ot.id,st.id

def auth(client,email):
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"Password123!"}).json()["access_token"];return {"Authorization":f"Bearer {token}"}

def test_override_substitute_and_original_denied():
    Session,entry_id,original_id,sub_id=setup_db();client=TestClient(app);admin=auth(client,"admin@example.com");original=auth(client,"original@example.com");sub=auth(client,"sub@example.com");today=datetime.now().date().isoformat()
    created=client.post("/api/v1/scheduling/overrides",headers=admin,json={"timetable_entry_id":entry_id,"override_date":today,"new_teacher_id":sub_id,"new_room":"R2","reason":"Original unavailable"});assert created.status_code==200,created.text;oid=created.json()["id"];assert client.patch(f"/api/v1/scheduling/overrides/{oid}",headers=admin,json={"status":"approved"}).status_code==200
    assert client.post(f"/api/v1/sessions/{entry_id}/start",headers=original).status_code==403
    current=client.get("/api/v1/teachers/me/current-sessions",headers=sub);assert current.status_code==200 and current.json()[0]["effective_teacher_id"]==sub_id and current.json()[0]["original_teacher_id"]==original_id
    started=client.post(f"/api/v1/sessions/{entry_id}/start",headers=sub);assert started.status_code==200,started.text
    assert client.post(f"/api/v1/sessions/{started.json()['id']}/finalize",headers=sub).status_code==200
    with Session() as db:assert db.get(TimetableEntry,entry_id).teacher_id==original_id
    app.dependency_overrides.clear()

def test_mixed_csv_import_creates_student_account():
    Session,_,_,_=setup_db();client=TestClient(app);admin=auth(client,"admin@example.com");csv=b"name,email,batch_name,section_name,phone\nValid Student,valid@example.com,2026,A,9800000000\nMissing Email,,2026,A,\nWrong Section,wrong@example.com,2026,Z,\n"
    response=client.post("/api/v1/imports/students",headers=admin,files={"file":("students.csv",io.BytesIO(csv),"text/csv")});assert response.status_code==200,response.text;data=response.json();assert(data["success_count"],data["failed_count"])==(1,2);messages=" ".join(x["error_message"] for x in data["errors"]);assert "email is required" in messages and "does not exist" in messages
    students=client.get("/api/v1/academic/students",headers=admin).json();assert any(x["email"]=="valid@example.com" and x["account_status"]=="Activated" for x in students)
    login=client.post("/api/v1/auth/login",json={"email":"valid@example.com","password":"Welcome123!"});assert login.status_code==200,login.text
    app.dependency_overrides.clear()

def test_registered_student_can_receive_password_setup_invitation():
    Session,_,_,_=setup_db();client=TestClient(app);admin=auth(client,"admin@example.com")
    csv=b"name,email,batch_name,section_name,phone\nExisting Student,existing@example.com,2026,A,\n"
    imported=client.post("/api/v1/imports/students",headers=admin,files={"file":("students.csv",io.BytesIO(csv),"text/csv")})
    assert imported.status_code==200,imported.text
    student=next(row for row in client.get("/api/v1/academic/students",headers=admin).json() if row["email"]=="existing@example.com")
    original_user_id=None
    with Session() as db:
        original_user_id=db.get(Student,student["id"]).user_id

    queued=client.post("/api/v1/academic/students/invitations",headers=admin,json={"student_ids":[student["id"]],"only_without_accounts":False})
    assert queued.status_code==200,queued.text
    assert queued.json()["sent"]==1
    assert queued.json()["password_setup_sent"]==1
    assert queued.json()["activation_sent"]==0
    refreshed=next(row for row in client.get("/api/v1/academic/students",headers=admin).json() if row["id"]==student["id"])
    assert refreshed["account_status"]=="Password Setup Queued" and refreshed["has_account"] is True

    with Session() as db:
        invitation=db.scalar(select(StudentInvitation).where(StudentInvitation.student_id==student["id"]))
        notification=db.scalar(select(Notification).where(Notification.related_entity=="student_invitation"))
        assert invitation and invitation.purpose==InvitationPurpose.PASSWORD_SETUP
        assert notification and notification.subject=="Set your AntimBench password"
        token=parse_qs(urlparse(notification.body.rsplit(" ",1)[-1]).query)["token"][0]

    validated=client.get(f"/api/v1/auth/activate/validate?token={token}")
    assert validated.status_code==200,validated.text
    assert validated.json()["mode"]=="password_setup" and validated.json()["account_exists"] is True
    completed=client.post("/api/v1/auth/activate",json={"token":token,"password":"NewPassword123!"})
    assert completed.status_code==200,completed.text

    with Session() as db:
        stored_student=db.get(Student,student["id"])
        stored_invitation=db.scalar(select(StudentInvitation).where(StudentInvitation.student_id==student["id"]))
        assert stored_student.user_id==original_user_id
        assert stored_invitation.status==InvitationStatus.ACTIVATED
    assert client.post("/api/v1/auth/login",json={"email":"existing@example.com","password":"Welcome123!"}).status_code==401
    assert client.post("/api/v1/auth/login",json={"email":"existing@example.com","password":"NewPassword123!"}).status_code==200
    assert client.post("/api/v1/auth/activate",json={"token":token,"password":"AnotherPassword123!"}).status_code==409
    app.dependency_overrides.clear()

def test_invitation_activation_is_single_use():
    Session,_,_,_=setup_db();token="secure-test-token";client=TestClient(app)
    with Session() as db:
        section=db.scalar(select(Section));student=Student(section_id=section.id,roll_number="INV-1",name="Invited",email="invite@example.com");db.add(student);db.flush();db.add(StudentInvitation(student_id=student.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=datetime.now(UTC)+timedelta(hours=1)));db.commit()
    assert client.get(f"/api/v1/auth/activate/validate?token={token}").status_code==200
    activated=client.post("/api/v1/auth/activate",json={"token":token,"password":"Password123!"});assert activated.status_code==200,activated.text
    assert client.post("/api/v1/auth/activate",json={"token":token,"password":"Password123!"}).status_code==409
    assert client.get("/api/v1/auth/activate/validate?token=bad").status_code==404
    app.dependency_overrides.clear()
