from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.identity import router as identity_router
from app.modules.identity.models import User, UserRole


@pytest.mark.parametrize("role", list(UserRole))
def test_every_role_can_upload_a_profile_photo(role, tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(identity_router, "PROFILE_MEDIA_DIR", tmp_path)

    def override():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        email = f"{role.value}@example.com"
        with session_factory() as db:
            db.add(User(name=role.value.title(), email=email, password_hash=hash_password("Password123!"), role=role))
            db.commit()

        image_stream = BytesIO()
        Image.new("RGB", (1, 1), "white").save(image_stream, format="PNG")
        client = TestClient(app)
        assert client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"}).status_code == 200
        avatar = client.post("/api/v1/auth/me/avatar", files={"image": ("portrait.png", image_stream.getvalue(), "image/png")})
        assert avatar.status_code == 200
        assert client.get(avatar.json()["avatar_url"]).status_code == 200
    finally:
        app.dependency_overrides.clear()
