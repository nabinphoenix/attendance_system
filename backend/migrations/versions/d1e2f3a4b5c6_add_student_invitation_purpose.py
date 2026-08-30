"""add student invitation purpose

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


invitation_purpose = postgresql.ENUM(
    "ACTIVATION",
    "PASSWORD_SETUP",
    name="invitationpurpose",
    create_type=False,
)


def upgrade() -> None:
    invitation_purpose.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "student_invitations",
        sa.Column(
            "purpose",
            invitation_purpose,
            nullable=False,
            server_default="ACTIVATION",
        ),
    )


def downgrade() -> None:
    op.drop_column("student_invitations", "purpose")
    invitation_purpose.drop(op.get_bind(), checkfirst=True)
