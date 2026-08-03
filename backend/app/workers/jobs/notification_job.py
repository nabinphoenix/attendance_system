import smtplib
from datetime import UTC,datetime
from email.message import EmailMessage
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.academic.models import Guardian,Student,Teacher
from app.modules.identity.models import User
from app.modules.operations.models import Notification,NotificationStatus
def recipient_address(db,n):
    if n.recipient_type=="guardian":
        guardian=db.get(Guardian,n.recipient_id);return db.get(User,guardian.user_id).email if guardian and guardian.user_id else None
    if n.recipient_type=="student":
        obj=db.get(Student,n.recipient_id);return obj.user.email if obj else None
    if n.recipient_type=="teacher":
        obj=db.get(Teacher,n.recipient_id);return obj.user.email if obj else None
    user=db.get(User,n.recipient_id);return user.email if user else None
def handle(payload:dict)->None:
    with SessionLocal() as db:
        n=db.get(Notification,int(payload["notification_id"]))
        if not n:return
        try:
            destination=recipient_address(db,n)
            if n.channel=="sms":print(f"[MOCK SMS] to {destination or n.recipient_id}: {n.body}")
            elif not settings.smtp_host:print(f"[MOCK EMAIL] to {destination or n.recipient_id}: {n.subject} — {n.body}")
            elif destination:
                message=EmailMessage();message["From"]=settings.smtp_from_email;message["To"]=destination;message["Subject"]=n.subject;message.set_content(n.body)
                with smtplib.SMTP(settings.smtp_host,settings.smtp_port) as smtp:
                    smtp.starttls()
                    if settings.smtp_username:smtp.login(settings.smtp_username,settings.smtp_password or "")
                    smtp.send_message(message)
            else:raise ValueError("Recipient has no deliverable email address")
            n.status=NotificationStatus.SENT;n.sent_at=datetime.now(UTC)
        except Exception as exc:n.status=NotificationStatus.FAILED;print(f"Notification {n.id} failed: {exc}")
        db.commit()
