from datetime import date,datetime,timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base,get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch,Program,Section,Student,Subject,Teacher
from app.modules.attendance.models import AttendanceMethod,AttendanceRecord,AttendanceStatus
from app.modules.course_completion.models import CoursePlan
from app.modules.crm.models import CasePriority,CaseStatus,StudentCase
from app.modules.identity.models import User,UserRole
from app.modules.scheduling.models import ClassSession,ScheduleOverride,SessionStatus,TimetableEntry

def phase4_db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override
    with Session() as db:
        p=Program(name="BCA");db.add(p);db.flush();b=Batch(name="2026",program_id=p.id);db.add(b);db.flush();section=Section(name="A",batch_id=b.id);db.add(section);db.flush();subject=Subject(name="Architecture",code="ARC",section_id=section.id);db.add(subject);db.flush();admin=User(name="Admin",email="admin4@example.com",password_hash=hash_password("Password123!"),role=UserRole.ADMIN);teacher_user=User(name="Teacher",email="teacher4@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER);student_user=User(name="Student",email="student4@example.com",password_hash=hash_password("Password123!"),role=UserRole.STUDENT);db.add_all([admin,teacher_user,student_user]);db.flush();teacher=Teacher(user_id=teacher_user.id,employee_code="T4");db.add(teacher);db.flush();student=Student(user_id=student_user.id,section_id=section.id,roll_number="R4",subjects=[subject]);db.add(student);db.flush();entry=TimetableEntry(teacher_id=teacher.id,subject_id=subject.id,section_id=section.id,day_of_week=0,start_time=datetime.strptime("09:00","%H:%M").time(),end_time=datetime.strptime("10:00","%H:%M").time(),room_name="R1",latitude=0,longitude=0);db.add(entry);db.flush();plan=CoursePlan(subject_id=subject.id,batch_id=b.id,planned_sessions=5);db.add(plan);db.commit();return Session,{"admin":admin.id,"teacher":teacher.id,"student":student.id,"subject":subject.id,"batch":b.id,"entry":entry.id,"plan":plan.id}

def token(client,email):return client.post("/api/v1/auth/login",json={"email":email,"password":"Password123!"}).json()["access_token"]

def test_course_completion_finalization_makeup_and_override():
    Session,ids=phase4_db();client=TestClient(app);th={"Authorization":f"Bearer {token(client,'teacher4@example.com')}"};ah={"Authorization":f"Bearer {token(client,'admin4@example.com')}"}
    with Session() as db:
        session_ids=[]
        for offset in range(3):
            s=ClassSession(timetable_entry_id=ids["entry"],session_date=date.today()-timedelta(days=offset),effective_teacher_id=ids["teacher"],effective_room="R1",status=SessionStatus.ACTIVE);db.add(s);db.flush();session_ids.append(s.id)
        db.commit()
    for sid in session_ids:assert client.post(f"/api/v1/sessions/{sid}/finalize",headers=th).status_code==200
    plans=client.get(f"/api/v1/course-completion/plans?batch_id={ids['batch']}&subject_id={ids['subject']}",headers=ah).json();assert plans[0]["conducted_sessions"]==3 and plans[0]["deficit"]==2
    suggestion=client.post(f"/api/v1/course-completion/plans/{ids['plan']}/suggest-makeup",headers=ah);assert suggestion.status_code==200,suggestion.text;data=suggestion.json();approved=client.patch(f"/api/v1/course-completion/suggestions/{data['id']}",headers=ah,json={"status":"approved"});assert approved.status_code==200,approved.text
    with Session() as db:
        override=db.scalar(select(ScheduleOverride).where(ScheduleOverride.override_date==date.fromisoformat(data["suggested_date"])));assert override and override.new_teacher_id==ids["teacher"] and override.new_room==data["suggested_room"]
    app.dependency_overrides.clear()

def test_risk_idempotency_and_database_partial_unique_index():
    Session,ids=phase4_db();client=TestClient(app);ah={"Authorization":f"Bearer {token(client,'admin4@example.com')}"}
    with Session() as db:
        for offset,status in enumerate([AttendanceStatus.PRESENT,AttendanceStatus.ABSENT,AttendanceStatus.ABSENT,AttendanceStatus.BUNK]):
            session=ClassSession(timetable_entry_id=ids["entry"],session_date=date.today()-timedelta(days=offset),effective_teacher_id=ids["teacher"],effective_room="R1",status=SessionStatus.COMPLETED);db.add(session);db.flush();db.add(AttendanceRecord(class_session_id=session.id,student_id=ids["student"],status=status,method=AttendanceMethod.FINALIZATION))
        db.commit()
    first=client.post("/api/v1/analytics/risk-evaluations/run",headers=ah).json();second=client.post("/api/v1/analytics/risk-evaluations/run",headers=ah).json();assert first["created"]==1 and second["created"]==0 and second["updated"]==1
    with Session() as db:
        cases=db.scalars(select(StudentCase)).all();assert len(cases)==1
        db.add(StudentCase(student_id=ids["student"],trigger_type="ATTENDANCE_LOW",scope_type="SUBJECT",scope_id=ids["subject"],status=CaseStatus.OPEN,priority=CasePriority.HIGH))
        with pytest.raises(IntegrityError):db.flush()
    app.dependency_overrides.clear()
