from datetime import date,timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base,get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch,Guardian,Program,Section,Student,Subject,Teacher
from app.modules.attendance.models import AttendanceMethod,AttendanceRecord,AttendanceStatus
from app.modules.identity.models import User,UserRole
from app.modules.operations.models import Notification
from app.modules.scheduling.models import ClassSession,SessionStatus,TimetableEntry

def setup_phase5():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override
    with Session() as db:
        p=Program(name="BCA");db.add(p);db.flush();b=Batch(name="2026",program_id=p.id);db.add(b);db.flush();section=Section(name="A",batch_id=b.id);db.add(section);db.flush();subject=Subject(name="Architecture",code="ARC",section_id=section.id);db.add(subject);db.flush();admin=User(name="Admin",email="admin5@example.com",password_hash=hash_password("Password123!"),role=UserRole.ADMIN);teacher_user=User(name="Teacher",email="teacher5@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER);db.add_all([admin,teacher_user]);db.flush();teacher=Teacher(user_id=teacher_user.id,employee_code="T5");db.add(teacher);db.flush();students=[]
        for i in range(2):
            u=User(name=f"Student {i}",email=f"student5{i}@example.com",password_hash=hash_password("Password123!"),role=UserRole.STUDENT);db.add(u);db.flush();s=Student(user_id=u.id,section_id=section.id,roll_number=f"R5{i}",subjects=[subject]);db.add(s);db.flush();students.append(s)
        db.add(Guardian(name="Test Guardian",student_id=students[0].id,phone="9800000000"));entry=TimetableEntry(teacher_id=teacher.id,subject_id=subject.id,section_id=section.id,day_of_week=0,start_time=__import__("datetime").time(9),end_time=__import__("datetime").time(10),room_name="R1",latitude=0,longitude=0);db.add(entry);db.flush()
        for offset in range(4):
            session=ClassSession(timetable_entry_id=entry.id,session_date=date.today()-timedelta(days=offset),effective_teacher_id=teacher.id,effective_room="R1",status=SessionStatus.COMPLETED);db.add(session);db.flush();db.add(AttendanceRecord(class_session_id=session.id,student_id=students[0].id,status=AttendanceStatus.ABSENT if offset else AttendanceStatus.PRESENT,method=AttendanceMethod.FINALIZATION));db.add(AttendanceRecord(class_session_id=session.id,student_id=students[1].id,status=AttendanceStatus.PRESENT,method=AttendanceMethod.FINALIZATION))
        db.commit();return Session,students[0].id,students[1].id
def auth(client,email):return {"Authorization":f"Bearer {client.post('/api/v1/auth/login',json={'email':email,'password':'Password123!'}).json()['access_token']}"}
def test_student_export_scope_csv_and_pdf():
    Session,own,other=setup_phase5();client=TestClient(app);headers=auth(client,"student50@example.com");start=(date.today()-timedelta(days=7)).isoformat();end=date.today().isoformat();csv=client.get(f"/api/v1/exports/attendance.csv?student_id={own}&date_from={start}&date_to={end}",headers=headers);assert csv.status_code==200 and "Student 0" in csv.text and csv.headers["content-disposition"].endswith('attendance_report.csv"');assert client.get(f"/api/v1/exports/attendance.csv?student_id={other}&date_from={start}&date_to={end}",headers=headers).status_code==403;pdf=client.get(f"/api/v1/exports/attendance.pdf?student_id={own}&date_from={start}&date_to={end}",headers=headers);assert pdf.status_code==200 and pdf.content.startswith(b"%PDF")
    app.dependency_overrides.clear()
def test_student_attendance_report_supports_date_range_and_day_subject_status():
    Session,own,_=setup_phase5();client=TestClient(app);headers=auth(client,"student50@example.com");start=(date.today()-timedelta(days=1)).isoformat();end=date.today().isoformat()
    response=client.get(f"/api/v1/analytics/my-attendance?date_from={start}&date_to={end}",headers=headers)
    assert response.status_code==200
    payload=response.json();assert payload["present"]==1 and payload["absent"]==1 and payload["total"]==2 and payload["overall_percentage"]==50
    assert [day["date"] for day in payload["days"]]==[end,start]
    assert payload["days"][0]["records"][0]["status"]=="present" and payload["days"][1]["records"][0]["status"]=="absent"
    assert payload["days"][0]["records"][0]["subject_name"]=="Architecture"
    assert client.get(f"/api/v1/analytics/my-attendance?date_from={end}&date_to={start}",headers=headers).status_code==422
    app.dependency_overrides.clear()
def test_risk_case_queues_guardian_notification():
    Session,own,_=setup_phase5();client=TestClient(app);headers=auth(client,"admin5@example.com");response=client.post("/api/v1/analytics/risk-evaluations/run",headers=headers);assert response.status_code==200 and response.json()["created"]==1
    with Session() as db:
        notification=db.scalar(select(Notification));assert notification and notification.recipient_type=="guardian" and "dropped below" in notification.body and "Architecture" in notification.body
    app.dependency_overrides.clear()
