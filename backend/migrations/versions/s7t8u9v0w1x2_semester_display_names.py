"""add batch-scoped semester display names

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
"""

from alembic import op
import sqlalchemy as sa


revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable preserves all existing IDs and relationships; callers display the
    # immutable number when a historical record has no custom label yet.
    op.add_column("cohort_semesters", sa.Column("display_name", sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column("cohort_semesters", "display_name")