"""pending combined routine section references

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "routine_pending_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("routine_entry_id", sa.Integer(), nullable=False),
        sa.Column("section_name", sa.String(length=50), nullable=False),
        sa.Column("intake_id", sa.Integer(), nullable=False),
        sa.Column("semester_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_section_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["intake_id"], ["intakes.id"]),
        sa.ForeignKeyConstraint(["resolved_section_id"], ["sections.id"]),
        sa.ForeignKeyConstraint(["routine_entry_id"], ["routine_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("routine_entry_id", "section_name", name="uq_routine_pending_entry_name"),
    )
    op.create_index("ix_routine_pending_sections_routine_entry_id", "routine_pending_sections", ["routine_entry_id"])
    op.add_column(
        "import_jobs",
        sa.Column("pending_section_references", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("import_jobs", "pending_section_references", server_default=None)


def downgrade():
    op.drop_column("import_jobs", "pending_section_references")
    op.drop_index("ix_routine_pending_sections_routine_entry_id", table_name="routine_pending_sections")
    op.drop_table("routine_pending_sections")
