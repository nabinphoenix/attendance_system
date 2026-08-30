"""add per-session attendance controls

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""

from alembic import op
import sqlalchemy as sa


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "class_sessions",
        sa.Column("self_checkin_window_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "class_sessions",
        sa.Column("challenge_rotation_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("class_sessions", "challenge_rotation_seconds")
    op.drop_column("class_sessions", "self_checkin_window_minutes")
