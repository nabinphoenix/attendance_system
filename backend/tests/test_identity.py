def test_health(client=None):
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/api/v1/identity/health").status_code == 200
