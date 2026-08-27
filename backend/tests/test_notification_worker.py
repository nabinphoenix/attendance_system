from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.identity.models import User, UserRole
from app.modules.operations.models import Notification, NotificationStatus
from app.modules.operations.service import queue_notification
from app.workers import worker
from app.workers.jobs import notification_job


class FakeSMTP:
    sent: list[object] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        return None

    def login(self, *args):
        return None

    def send_message(self, message):
        self.sent.append(message)


def test_worker_delivers_committed_pending_notifications(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        user = User(name="Recipient", email="recipient@example.com", password_hash="unused", role=UserRole.ADMIN)
        db.add(user)
        db.flush()
        queue_notification(db, "user", user.id, "Attendance update", "Your attendance changed.")
        db.commit()

    FakeSMTP.sent = []
    monkeypatch.setattr(worker, "SessionLocal", Session)
    monkeypatch.setattr(notification_job, "SessionLocal", Session)
    monkeypatch.setattr(notification_job.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notification_job.settings, "smtp_host", "smtp.example.com")

    assert worker.process_pending_notifications() == 1
    with Session() as db:
        notification = db.scalar(__import__("sqlalchemy").select(Notification))
        assert notification.status == NotificationStatus.SENT
        assert notification.sent_at is not None
    assert len(FakeSMTP.sent) == 1
