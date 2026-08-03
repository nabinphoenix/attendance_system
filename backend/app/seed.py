from datetime import datetime, timedelta
from sqlalchemy import select
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.modules.academic.models import Batch, Guardian, Program, Section, Student, Subject, Teacher
from app.modules.attendance import models as attendance_models
from app.modules.identity.models import User, UserRole
from app.modules.operations import models as operations_models
from app.modules.scheduling.models import TimetableEntry

TEACHER=("teacher@antimbench.example.com","Teacher123!")
ADMIN=("admin@antimbench.example.com","Admin123!")
SUBSTITUTE=("substitute@antimbench.example.com","Teacher123!")
PARENT=("parent@antimbench.example.com","Parent123!")
STUDENTS=[(f"student{i}@antimbench.example.com","Student123!") for i in range(1,5)]

def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email==TEACHER[0])):
            print("Seed data already exists.")
        else:
            program=Program(name="Bachelor of Computer Applications"); db.add(program); db.flush()
            batch=Batch(name="2026",program_id=program.id); db.add(batch); db.flush()
            section=Section(name="A",batch_id=batch.id); db.add(section); db.flush()
            subject=Subject(name="Software Architecture",code="SWA601",section_id=section.id); db.add(subject); db.flush()
            teacher_user=User(name="Demo Teacher",email=TEACHER[0],password_hash=hash_password(TEACHER[1]),role=UserRole.TEACHER); db.add(teacher_user); db.flush()
            teacher=Teacher(user_id=teacher_user.id,employee_code="T-001"); db.add(teacher); db.flush()
            admin=User(name="Demo Admin",email=ADMIN[0],password_hash=hash_password(ADMIN[1]),role=UserRole.ADMIN);db.add(admin)
            substitute_user=User(name="Substitute Teacher",email=SUBSTITUTE[0],password_hash=hash_password(SUBSTITUTE[1]),role=UserRole.TEACHER);db.add(substitute_user);db.flush();db.add(Teacher(user_id=substitute_user.id,employee_code="T-002"))
            created_students=[]
            for i,(email,password) in enumerate(STUDENTS,1):
                user=User(name=f"Demo Student {i}",email=email,password_hash=hash_password(password),role=UserRole.STUDENT); db.add(user); db.flush(); student=Student(user_id=user.id,section_id=section.id,roll_number=f"BCA-{i:02}",subjects=[subject]);db.add(student);db.flush();created_students.append(student)
            parent=User(name="Demo Parent",email=PARENT[0],password_hash=hash_password(PARENT[1]),role=UserRole.PARENT);db.add(parent);db.flush();db.add(Guardian(name="Demo Guardian",student_id=created_students[0].id,user_id=parent.id,phone="9800000000"))
            now=datetime.now(); db.add(TimetableEntry(teacher_id=teacher.id,subject_id=subject.id,section_id=section.id,day_of_week=now.weekday(),start_time=(now-timedelta(hours=1)).time().replace(microsecond=0),end_time=(now+timedelta(hours=1)).time().replace(microsecond=0),room_name="Architecture Lab",latitude=27.7172,longitude=85.3240)); db.commit(); print("Created immediately active demo timetable.")
        parent=db.scalar(select(User).where(User.email==PARENT[0]))
        first_student=db.scalar(select(Student).join(User,Student.user_id==User.id).where(User.email==STUDENTS[0][0]))
        if first_student and not parent:
            parent=User(name="Demo Parent",email=PARENT[0],password_hash=hash_password(PARENT[1]),role=UserRole.PARENT);db.add(parent);db.flush()
        if first_student and parent and not db.scalar(select(Guardian).where(Guardian.student_id==first_student.id,Guardian.user_id==parent.id)):
            db.add(Guardian(name="Demo Guardian",student_id=first_student.id,user_id=parent.id,phone="9800000000"))
        db.commit()
    print(f"Teacher: {TEACHER[0]} / {TEACHER[1]}")
    print(f"Substitute: {SUBSTITUTE[0]} / {SUBSTITUTE[1]}")
    print(f"Admin: {ADMIN[0]} / {ADMIN[1]}")
    print(f"Parent: {PARENT[0]} / {PARENT[1]}")
    for email,password in STUDENTS: print(f"Student: {email} / {password}")

if __name__=="__main__": run()
