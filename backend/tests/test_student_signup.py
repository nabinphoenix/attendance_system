from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.main import app
from app.modules.academic.models import Batch, Program, Section, Student
from app.modules.identity.models import User, UserRole

def test_student_signup_creates_linked_records_and_rejects_duplicate():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine);Base.metadata.create_all(engine)
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override
    with Session() as db:
        program=Program(name="BCA");db.add(program);db.flush();batch=Batch(name="2026",program_id=program.id);db.add(batch);db.flush();section=Section(name="A",batch_id=batch.id);db.add(section);db.commit();batch_id=batch.id;section_id=section.id
    client=TestClient(app);payload={"name":"New Student","email":"new.student@example.com","password":"Secure123!","batch_id":batch_id,"section_id":section_id}
    assert client.get("/api/v1/academic/batches").status_code==200
    created=client.post("/api/v1/auth/signup",json=payload);assert created.status_code==201 and created.json()["access_token"]
    with Session() as db:
        user=db.scalar(select(User).where(User.email==payload["email"]));assert user and user.role==UserRole.STUDENT
        assert db.scalar(select(func.count()).select_from(Student).where(Student.user_id==user.id))==1
    duplicate=client.post("/api/v1/auth/signup",json=payload);assert duplicate.status_code==409 and "already exists" in duplicate.json()["detail"]
    app.dependency_overrides.clear()
