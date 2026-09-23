import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.academic.models import Guardian, Student, Teacher
from app.modules.identity.models import User
from app.modules.operations.models import Notification, NotificationStatus
from app.modules.operations.email_templates import plain_text_email_html


def send_email(destination: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Shared SMTP transport for queued notifications and ephemeral recovery mail."""
    if not settings.smtp_host:
        raise ValueError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = destination
    message["Subject"] = subject
    message.set_content(body)
    message.add_alternative(html_body or plain_text_email_html(subject, body), subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


def send_password_reset_email(destination: str, token: str) -> None:
    # Fragment is never sent in HTTP requests/referrers or access logs.
    url = f"{settings.frontend_url.rstrip('/')}/reset-password#token={token}"
    body = (f"Reset your AntimBench password using this link:\n{url}\n\n"
            f"This single-use link expires in {settings.reset_token_expire_minutes} minutes. "
            "If you did not request it, you can ignore this email.")
    try:
        send_email(destination, "Reset your AntimBench password", body)
    except Exception:
        # SMTP exceptions may contain message content. Never log recovery secrets.
        import logging
        logging.getLogger(__name__).warning("Password reset email delivery failed; check SMTP configuration")


def recipient_address(db: Session, notification: Notification) -> str | None:
    if notification.recipient_type == "guardian":
        guardian = db.get(Guardian, notification.recipient_id)
        return db.get(User, guardian.user_id).email if guardian and guardian.user_id else None
    if notification.recipient_type == "student":
        student = db.get(Student, notification.recipient_id)
        return student.user.email if student and student.user else (student.email if student else None)
    if notification.recipient_type == "teacher":
        teacher = db.get(Teacher, notification.recipient_id)
        return teacher.user.email if teacher else None
    user = db.get(User, notification.recipient_id)
    return user.email if user else None


def deliver_notification(db: Session, notification: Notification) -> None:
    """Send one locked notification and persist the terminal delivery status."""

    try:
        if notification.channel != "email":
            raise ValueError(f"Unsupported notification channel: {notification.channel}")
        if not settings.smtp_host:
            raise ValueError("SMTP is not configured")
        destination = recipient_address(db, notification)
        if not destination:
            raise ValueError("Recipient has no deliverable email address")
        send_email(destination, notification.subject, notification.body, notification.html_body)
        if notification.related_entity == "student_invitation":
            notification.body = "Secure student account setup email delivered."
            notification.html_body = "Secure student account setup email delivered."
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(UTC)
    except Exception as exc:
        notification.status = NotificationStatus.FAILED
        print(f"Notification {notification.id} failed: {exc}")


def handle(payload: dict) -> bool:
    """Claim and deliver one pending notification. Returns whether work was found."""

    notification_id = int(payload["notification_id"])
    with SessionLocal() as db:
        notification = db.scalar(
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.status == NotificationStatus.PENDING,
            )
            .with_for_update(skip_locked=True)
        )
        if not notification:
            return False
        deliver_notification(db, notification)
        db.commit()
        return True
