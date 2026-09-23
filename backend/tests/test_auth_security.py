"""Authentication security contract, with no external mail or production database."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password, hash_password
from app.main import app
from app.modules.identity.models import AuthRateLimit, User, UserRole
from app.modules.identity import router as identity_router
from app.modules.operations.models import AuditLog, Notification
from app.modules.platform.models import College
from tests.attendance_database import make_attendance_engine, dispose_attendance_engine

OLD = "Original123!"
NEW = "FreshPassword123!"


@pytest.fixture
def security(monkeypatch):
    engine, schema = make_attendance_engine()
    factory = sessionmaker(bind=engine)
    sent = []
    monkeypatch.setattr(identity_router, "send_password_reset_email", lambda email, token: sent.append((email, token)))
    def override():
        with factory() as db:
            db.info["college_id"] = -1
            yield db
    app.dependency_overrides[get_db] = override
    with factory() as db:
        db.add(College(id=2, name="Other college", slug="other", is_active=True))
        db.flush()
        fixture_password = hash_password(OLD)
        for i, role in enumerate(UserRole, 1):
            db.add(User(id=i, name=role.value, email=f"{role.value}@example.com", password_hash=fixture_password,
                        role=role, college_id=None if role == UserRole.SUPER_ADMIN else 1))
        db.add(User(id=99, name="Other", email="other@example.com", password_hash=fixture_password, role=UserRole.STUDENT, college_id=2))
        db.commit()
    with TestClient(app) as client:
        yield client, factory, sent, engine
    app.dependency_overrides.clear()
    dispose_attendance_engine(engine, schema)


def login(client, role="student", password=OLD):
    return client.post("/api/v1/auth/login", json={"email": f"{role}@example.com", "password": password})


def request_reset(client, sent, role="student"):
    response = client.post("/api/v1/auth/forgot-password", json={"email": f"{role}@example.com"})
    assert response.status_code == 200
    return sent[-1][1]


def reset(client, token, password=NEW):
    return client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": password, "confirm_password": password})


@pytest.mark.parametrize("role", [role.value for role in UserRole])
def test_fifth_attempt_locks_every_role_and_correct_password_is_rejected(security, role):
    client, factory, sent, _ = security
    for attempt in range(1, 6):
        response = login(client, role, "wrong")
        assert response.status_code == (423 if attempt == 5 else 401)
        with factory() as db:
            user = db.scalar(select(User).where(User.email == f"{role}@example.com"))
            assert user.failed_login_attempts == attempt
            assert user.is_locked == (attempt == 5)
            assert user.last_failed_login_at is not None
            assert (user.locked_at is not None) == (attempt == 5)
    assert login(client, role).status_code == 423
    assert login(client, role, "wrong again").status_code == 423
    with factory() as db:
        user = db.scalar(select(User).where(User.email == f"{role}@example.com"))
        assert user.failed_login_attempts == 5
        assert len(db.scalars(select(AuditLog).where(AuditLog.action == "auth.account_locked")).all()) == 1


def test_success_resets_consecutive_attempts(security):
    client, factory, _, _ = security
    for _ in range(4):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 200
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.com"))
        assert user.failed_login_attempts == 0
        assert user.last_failed_login_at is None
        assert not user.is_locked
    assert login(client, password="wrong").status_code == 401


def test_recovery_changes_password_unlocks_consumes_token_and_revokes_sessions(security):
    client, factory, sent, _ = security
    old_token = login(client).json()["access_token"]
    for _ in range(5): login(client, password="wrong")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    token = request_reset(client, sent)
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.com"))
        assert user.reset_token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert db.scalars(select(Notification)).all() == []
    for _ in range(2):
        assert client.post("/api/v1/auth/reset-password/validate", json={"token": token}).status_code == 200
    assert reset(client, token).status_code == 200
    assert reset(client, token).status_code == 400
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.com"))
        assert verify_password(NEW, user.password_hash)
        assert not verify_password(OLD, user.password_hash)
        assert not user.is_locked and user.failed_login_attempts == 0
        assert user.locked_at is None and user.last_failed_login_at is None
        assert user.reset_token_hash is None and user.reset_expires_at is None
        events = db.scalars(select(AuditLog)).all()
        assert {"auth.password_reset_requested", "auth.password_reset_completed", "auth.account_locked"} <= {event.action for event in events}
        assert all(token not in event.details and NEW not in event.details and user.password_hash not in event.details for event in events)
    assert login(client, password=NEW).status_code == 200


def test_reset_revokes_unlocked_active_bearer_and_cookie_sessions(security):
    client, _, sent, _ = security
    old = login(client).json()["access_token"]
    old_cookie = client.cookies.get(settings.auth_cookie_name)
    token = request_reset(client, sent)
    assert reset(client, token).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    client.cookies.set(settings.auth_cookie_name, old_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_unknown_email_and_inactive_account_have_same_response_and_no_email(security):
    client, factory, sent, _ = security
    known = client.post("/api/v1/auth/forgot-password", json={"email": "student@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    with factory() as db:
        db.scalar(select(User).where(User.email == "teacher@example.com")).is_active = False
        db.commit()
    inactive = client.post("/api/v1/auth/forgot-password", json={"email": "teacher@example.com"})
    assert known.status_code == unknown.status_code == inactive.status_code == 200
    assert known.json() == unknown.json() == inactive.json()
    assert len(sent) == 1


def test_invalid_and_expired_challenges_cannot_change_password(security):
    client, factory, sent, _ = security
    assert reset(client, "x" * 43).status_code == 400
    token = request_reset(client, sent)
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.com"))
        user.reset_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert reset(client, token).status_code == 400
    assert client.post("/api/v1/auth/reset-password/validate", json={"token": token}).status_code == 400
    assert login(client).status_code == 200


def test_new_challenge_replaces_old_challenge_and_policy_is_enforced(security):
    client, factory, sent, _ = security
    first = request_reset(client, sent)
    with factory() as db:
        db.scalar(select(User).where(User.email == "student@example.com")).reset_requested_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
    second = request_reset(client, sent)
    assert first != second and reset(client, first).status_code == 400
    for weak in ["password", "12345678", "        ", "x" * 20, "a" * 73]:
        assert reset(client, second, weak).status_code == 422
    assert client.post("/api/v1/auth/reset-password", json={"token": second, "new_password": NEW, "confirm_password": OLD}).status_code == 422
    assert reset(client, second).status_code == 200


@pytest.mark.parametrize("admin", ["admin", "super_admin"])
def test_admin_unlock_preserves_password_and_audits_actor(security, admin):
    client, factory, _, _ = security
    for _ in range(5): login(client, password="wrong")
    assert login(client, admin).status_code == 200
    with factory() as db:
        target = db.scalar(select(User).where(User.email == "student@example.com"))
        target_id, before_hash = target.id, target.password_hash
        actor_id = db.scalar(select(User.id).where(User.email == f"{admin}@example.com"))
    prefix = "platform/" if admin == "super_admin" else ""
    response = client.post(f"/api/v1/{prefix}users/{target_id}/unlock")
    assert response.status_code == 200, response.text
    assert response.json()["failed_login_attempts"] == 0
    assert not response.json()["is_locked"]
    with factory() as db:
        assert db.get(User, target_id).password_hash == before_hash
        event = db.scalar(select(AuditLog).where(AuditLog.action == "auth.account_unlocked"))
        assert event.actor_id == actor_id and event.college_id == 1
    assert login(client).status_code == 200


def test_unlock_authorization_and_tenant_boundaries(security):
    client, factory, _, _ = security
    assert login(client).status_code == 200
    assert client.post("/api/v1/users/99/unlock").status_code == 403
    assert client.post("/api/v1/platform/users/99/unlock").status_code == 403
    assert login(client, "admin").status_code == 200
    assert client.post("/api/v1/users/99/unlock").status_code == 404
    with factory() as db:
        super_id = db.scalar(select(User.id).where(User.role == UserRole.SUPER_ADMIN))
    assert client.post(f"/api/v1/users/{super_id}/unlock").status_code in (403, 404)
    assert login(client, "super_admin").status_code == 200
    assert client.post("/api/v1/platform/users/99/unlock").status_code == 200


def test_login_request_and_verification_rate_limits_persist(security, monkeypatch):
    client, factory, sent, _ = security
    monkeypatch.setattr(settings, "login_rate_limit", 5)
    for _ in range(5): assert login(client, "unknown").status_code == 401
    assert login(client, "unknown").status_code == 429
    monkeypatch.setattr(settings, "reset_request_ip_limit", 2)
    for _ in range(2): assert client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"}).status_code == 200
    response = client.post("/api/v1/auth/forgot-password", json={"email": "student@example.com"})
    assert response.status_code == 429 and response.headers["Retry-After"]
    monkeypatch.setattr(settings, "reset_verify_rate_limit", 2)
    assert reset(client, "x" * 43).status_code == 400
    assert client.post("/api/v1/auth/reset-password/validate", json={"token": "x" * 43}).status_code == 400
    assert reset(client, "x" * 43).status_code == 429
    with factory() as db:
        keys = db.scalars(select(AuthRateLimit.key)).all()
        assert keys and all(len(key) == 64 and "@" not in key for key in keys)
        for bucket in db.scalars(select(AuthRateLimit)).all(): bucket.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert login(client, "unknown").status_code == 401


def test_reset_email_cooldown_and_per_email_limit(security):
    client, factory, sent, _ = security
    token = request_reset(client, sent)
    for _ in range(3): assert request_reset(client, sent) == token
    assert len(sent) == 1
    # A different IP cannot bypass the shared per-address delivery limit.
    with TestClient(app, client=("203.0.113.8", 45000)) as second_client:
        assert request_reset(second_client, sent) == token
    assert len(sent) == 1


def test_postgres_concurrent_attempts_and_single_use_reset(security):
    client, factory, sent, engine = security
    if engine.dialect.name != "postgresql": pytest.skip("Requires isolated PostgreSQL schema")
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(lambda _: login(TestClient(app), password="wrong").status_code, range(5)))
    assert sorted(codes) == [401, 401, 401, 401, 423]
    token = request_reset(client, sent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: reset(TestClient(app), token).status_code, range(2)))
    assert sorted(codes) == [200, 400]


def test_reset_email_reuses_smtp_and_never_logs_token(monkeypatch, caplog):
    from app.workers.jobs import notification_job
    from tests.test_notification_worker import FakeSMTP
    FakeSMTP.sent = []
    monkeypatch.setattr(notification_job.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    token = "test-secret-for-delivery-only"
    notification_job.send_password_reset_email("student@example.com", token)
    assert len(FakeSMTP.sent) == 1
    message = FakeSMTP.sent[0]
    assert message["To"] == "student@example.com"
    assert f"/reset-password#token={token}" in message.get_body(preferencelist=("plain",)).get_content()
    def fail(*args, **kwargs):
        raise RuntimeError(f"SMTP error containing {token}")
    monkeypatch.setattr(notification_job, "send_email", fail)
    notification_job.send_password_reset_email("student@example.com", token)
    assert "delivery failed" in caplog.text
    assert token not in caplog.text
