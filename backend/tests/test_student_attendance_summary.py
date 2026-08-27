from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.academic.models import Batch, Program, Section, Student
from app.modules.identity.models import User, UserRole


def test_student_can_read_only_their_attendance_summary():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with Session() as db:
        program = Program(name="BCA")
        db.add(program)
        db.flush()
        batch = Batch(name="2026", program_id=program.id)
        db.add(batch)
        db.flush()
        section = Section(name="A", batch_id=batch.id)
        db.add(section)
        db.flush()
        user = User(name="Student", email="student@example.com", password_hash=hash_password("Password123!"), role=UserRole.STUDENT)
        db.add(user)
        db.flush()
        db.add(Student(user_id=user.id, section_id=section.id, roll_number="A-001", name=user.name, email=user.email))
        db.commit()

    client = TestClient(app)
    login = client.post("/api/v1/auth/login", json={"email": "student@example.com", "password": "Password123!"})
    assert login.status_code == 200
    response = client.get("/api/v1/analytics/my-attendance-summary")
    assert response.status_code == 200
    assert response.json() == {
        "student_id": 1,
        "present": 0,
        "absent": 0,
        "total": 0,
        "overall_percentage": 0,
        "subjects": [],
        "attendance_threshold_percent": 75,
        "minimum_observations": 4,
    }
    exported = client.get("/api/v1/analytics/my-attendance-summary.csv")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].endswith('my_attendance_analysis.csv"')
    app.dependency_overrides.clear()
