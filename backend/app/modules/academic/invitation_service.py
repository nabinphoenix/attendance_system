import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import User
from app.modules.operations.service import queue_notification
from app.modules.operations.email_templates import invitation_email

from .models import InvitationPurpose, InvitationStatus, Student, StudentInvitation


def issue_student_invitation(
    db: Session,
    student: Student,
    account: User | None,
    *,
    welcome: bool = False,
) -> StudentInvitation:
    """Create one current account-setup link and queue its durable email."""

    email = account.email if account else student.email
    if not email:
        raise ValueError("Student has no email address")

    for previous in db.scalars(
        select(StudentInvitation).where(
            StudentInvitation.student_id == student.id,
            StudentInvitation.status == InvitationStatus.SENT,
        )
    ).all():
        previous.status = InvitationStatus.REVOKED

    purpose = InvitationPurpose.PASSWORD_SETUP if account else InvitationPurpose.ACTIVATION
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.invitation_expire_hours)
    invitation = StudentInvitation(
        student_id=student.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        status=InvitationStatus.SENT,
        purpose=purpose,
        expires_at=expires_at,
    )
    db.add(invitation)
    db.flush()

    application_url = settings.frontend_url.rstrip("/")
    setup_url = f"{application_url}/activate?token={token}"
    student_name = student.name or (account.name if account else None) or "Student"

    subject, body, html_body = invitation_email(
        student_name=student_name,
        email=email,
        setup_url=setup_url,
        expires_hours=settings.invitation_expire_hours,
        welcome=welcome,
        has_account=account is not None,
    )
    queue_notification(
        db,
        "student",
        student.id,
        subject,
        body,
        "student_invitation",
        invitation.id,
        html_body=html_body,
    )
    return invitation
