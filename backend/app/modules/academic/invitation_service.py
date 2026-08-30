import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import User
from app.modules.operations.service import queue_notification

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

    if welcome:
        subject = "Your AntimBench student account is ready"
        body = (
            f"Hello {student_name},\n\n"
            "Your AntimBench student account has been created.\n"
            f"Sign-in email: {email}\n\n"
            "For your security, choose your own password using the single-use setup link below.\n\n"
            f"After you save your password, visit {application_url} and sign in with "
            "your registered email address and the password you created.\n\n"
            f"This setup link expires in {settings.invitation_expire_hours} hours.\n\n"
            f"Complete account setup: {setup_url}"
        )
    elif purpose == InvitationPurpose.PASSWORD_SETUP:
        subject = "Set your AntimBench password"
        body = (
            f"Hello {student_name}, set a new password for your existing AntimBench "
            f"account by opening this secure link before it expires: {setup_url}"
        )
    else:
        subject = "Activate your AntimBench account"
        body = (
            f"Hello {student_name}, activate your account by opening this link before "
            f"it expires: {setup_url}"
        )

    queue_notification(
        db,
        "student",
        student.id,
        subject,
        body,
        "student_invitation",
        invitation.id,
    )
    return invitation
