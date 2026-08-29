from fastapi.testclient import TestClient
from app.main import app

def test_public_student_signup_is_disabled():
    client = TestClient(app)
    response = client.post("/api/v1/auth/signup", json={})
    assert response.status_code == 404
