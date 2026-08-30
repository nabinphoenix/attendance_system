"""allow multiple attendance sessions for one class on a day

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""

from alembic import op


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_session_entry_date", "class_sessions", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_session_entry_date",
        "class_sessions",
        ["timetable_entry_id", "session_date"],
    )
