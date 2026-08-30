from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.identity.models import User, UserRole
from app.modules.identity import router as identity_router


def test_user_can_update_profile_password_and_avatar(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(identity_router, "PROFILE_MEDIA_DIR", tmp_path)

    def override():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        with session_factory() as db:
            db.add(User(name="Original Name", email="profile@example.com", password_hash=hash_password("Original123!"), role=UserRole.STUDENT))
            db.commit()

        client = TestClient(app)
        assert client.post("/api/v1/auth/login", json={"email": "profile@example.com", "password": "Original123!"}).status_code == 200
        missing_password = client.patch("/api/v1/auth/me", json={"name": "Updated Name", "email": "updated@example.com"})
        assert missing_password.status_code == 422

        profile = client.patch("/api/v1/auth/me", json={"name": "Updated Name", "email": "updated@example.com", "current_password": "Original123!"})
        assert profile.status_code == 200
        assert profile.json()["name"] == "Updated Name"
        assert profile.json()["email"] == "updated@example.com"

        assert client.post("/api/v1/auth/me/password", json={"current_password": "wrong", "new_password": "NewPassword123!"}).status_code == 422
        assert client.post("/api/v1/auth/me/password", json={"current_password": "Original123!", "new_password": "NewPassword123!"}).status_code == 204

        image_stream = BytesIO()
        Image.new("RGB", (1, 1), "white").save(image_stream, format="PNG")
        # Some browsers label image files as application/octet-stream. The
        # server should validate the actual image data rather than reject it.
        avatar = client.post("/api/v1/auth/me/avatar", files={"image": ("portrait.png", image_stream.getvalue(), "application/octet-stream")})
        assert avatar.status_code == 200
        assert avatar.json()["avatar_url"].startswith("/api/v1/profile-media/")
        assert client.get(avatar.json()["avatar_url"]).status_code == 200

        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.post("/api/v1/auth/login", json={"email": "profile@example.com", "password": "Original123!"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": "updated@example.com", "password": "NewPassword123!"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
