"""add routine entry section membership

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routine_entry_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("routine_entry_id", sa.Integer(), sa.ForeignKey("routine_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.UniqueConstraint("routine_entry_id", "section_id", name="uq_routine_entry_section"),
    )
    # Every pre-existing single-section entry remains visible through the bridge.
    op.execute("INSERT INTO routine_entry_sections (routine_entry_id, section_id) SELECT id, section_id FROM routine_entries")


def downgrade() -> None:
    op.drop_table("routine_entry_sections")
