from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.identity.models import User, UserRole


def test_admin_can_update_a_room_from_the_master_data_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        with Session() as db:
            db.add(User(
                name="Admin",
                email="admin@example.com",
                password_hash=hash_password("Password123!"),
                role=UserRole.ADMIN,
            ))
            db.commit()

        login = client.post("/api/v1/auth/login", json={
            "email": "admin@example.com",
            "password": "Password123!",
        })
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        block = client.post("/api/v1/academic/blocks", headers=headers, json={"name": "Block A"})
        assert block.status_code == 200, block.text
        room = client.post("/api/v1/academic/rooms", headers=headers, json={
            "block_id": block.json()["id"],
            "name": "Codespace",
            "room_type": "lecture",
            "capacity": 60,
        })
        assert room.status_code == 200, room.text

        updated = client.patch(f"/api/v1/academic/rooms/{room.json()['id']}", headers=headers, json={
            "name": "Codespace Lab",
            "room_type": "laboratory",
            "capacity": 40,
        })

        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Codespace Lab"
        assert updated.json()["room_type"] == "laboratory"
        assert updated.json()["capacity"] == 40
        assert updated.json()["block_id"] == block.json()["id"]
    finally:
        app.dependency_overrides.clear()
