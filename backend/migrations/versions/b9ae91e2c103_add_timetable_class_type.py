"""add timetable class type

Revision ID: b9ae91e2c103
Revises: 9647971e5956
"""
from alembic import op
import sqlalchemy as sa

revision = "b9ae91e2c103"
down_revision = "9647971e5956"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("timetable_entries") as batch_op:
        batch_op.add_column(sa.Column("class_type", sa.String(length=20), nullable=False, server_default="lecture"))


def downgrade() -> None:
    with op.batch_alter_table("timetable_entries") as batch_op:
        batch_op.drop_column("class_type")
