from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch, Program, Section, Student, Subject, Teacher
from app.modules.attendance.models import AttendanceChange, AttendanceRecord, AttendanceStatus
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import AuditLog
from app.modules.scheduling.models import TimetableEntry

def test_full_attendance_vertical_slice():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool); TestSession=sessionmaker(bind=engine); Base.metadata.create_all(engine)
    def override_db():
        with TestSession() as db: yield db
    app.dependency_overrides[get_db]=override_db
    with TestSession() as db:
        program=Program(name="BCA");db.add(program);db.flush();batch=Batch(name="2026",program_id=program.id);db.add(batch);db.flush();section=Section(name="A",batch_id=batch.id);db.add(section);db.flush();subject=Subject(name="Architecture",code="ARC",section_id=section.id);db.add(subject);db.flush()
        tu=User(name="Teacher",email="teacher@example.com",password_hash=hash_password("Password123!"),role=UserRole.TEACHER);db.add(tu);db.flush();teacher=Teacher(user_id=tu.id,employee_code="T1");db.add(teacher);db.flush()
        students=[]
        for i in range(2):
            u=User(name=f"Student {i}",email=f"student{i}@example.com",password_hash=hash_password("Password123!"),role=UserRole.STUDENT);db.add(u);db.flush();s=Student(user_id=u.id,section_id=section.id,roll_number=f"R{i}",subjects=[subject]);db.add(s);students.append(s)
        now=datetime.now();entry=TimetableEntry(teacher_id=teacher.id,subject_id=subject.id,section_id=section.id,day_of_week=now.weekday(),start_time=(now-timedelta(hours=1)).time(),end_time=(now+timedelta(hours=1)).time(),room_name="Lab",latitude=27.7172,longitude=85.3240);db.add(entry);db.commit();entry_id=entry.id
    client=TestClient(app)
    def login(email):
        response=client.post("/api/v1/auth/login",json={"email":email,"password":"Password123!"})
        assert response.status_code==200,response.text
        return response.json()["access_token"]
    teacher_headers={"Authorization":f"Bearer {login('teacher@example.com')}"}; student_headers={"Authorization":f"Bearer {login('student0@example.com')}"}
    started=client.post(f"/api/v1/sessions/{entry_id}/start",headers=teacher_headers);assert started.status_code==200,started.text;session_id=started.json()["id"]
    token=client.get(f"/api/v1/sessions/{session_id}/qr",headers=teacher_headers).json()["token"]
    payload={"qr_token":token,"latitude":27.7172,"longitude":85.3240,"accuracy":5}
    checked=client.post("/api/v1/check-ins",headers=student_headers,json=payload);assert checked.status_code==200,checked.text
    assert client.post("/api/v1/check-ins",headers=student_headers,json=payload).status_code==409
    final=client.post(f"/api/v1/sessions/{session_id}/finalize",headers=teacher_headers);assert final.status_code==200,final.text
    rows=final.json();assert {r["status"] for r in rows}=={"present","absent"};absent=next(r for r in rows if r["status"]=="absent")
    changed=client.patch(f"/api/v1/attendance/{absent['attendance_id']}",headers=teacher_headers,json={"status":"leave","reason":"Approved medical evidence"});assert changed.status_code==200,changed.text
    with TestSession() as db:
        assert db.scalar(select(AttendanceChange)) is not None;assert db.scalar(select(AuditLog)) is not None;assert db.get(AttendanceRecord,absent["attendance_id"]).status==AttendanceStatus.LEAVE
    app.dependency_overrides.clear()
