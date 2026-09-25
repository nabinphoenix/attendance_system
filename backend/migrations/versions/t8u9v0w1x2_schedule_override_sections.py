"""persist section membership for dated routine overrides

Revision ID: t8u9v0w1x2
Revises: s7t8u9v0w1x2
"""

from alembic import op
import sqlalchemy as sa


revision = "t8u9v0w1x2"
down_revision = "s7t8u9v0w1x2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_override_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=False),
        sa.Column(
            "schedule_override_id",
            sa.Integer(),
            sa.ForeignKey("schedule_overrides.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.UniqueConstraint(
            "schedule_override_id", "section_id", name="uq_schedule_override_section"
        ),
    )
    op.create_index(
        "ix_schedule_override_sections_college_id",
        "schedule_override_sections",
        ["college_id"],
    )
    op.create_index(
        "ix_schedule_override_sections_schedule_override_id",
        "schedule_override_sections",
        ["schedule_override_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            'CREATE TRIGGER college_owner_immutable BEFORE UPDATE ON "schedule_override_sections" '
            "FOR EACH ROW EXECUTE FUNCTION enforce_college_reference()"
        )
        for column, table in (
            ("schedule_override_id", "schedule_overrides"),
            ("section_id", "sections"),
        ):
            op.execute(
                "CREATE TRIGGER college_ref_{column} BEFORE INSERT OR UPDATE ON "
                '"schedule_override_sections" FOR EACH ROW EXECUTE FUNCTION '
                "enforce_college_reference('{table}', '{column}', 'relation')".format(
                    column=column, table=table
                )
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS college_ref_section_id ON schedule_override_sections"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS college_ref_schedule_override_id ON schedule_override_sections"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS college_owner_immutable ON schedule_override_sections"
        )
    op.drop_index(
        "ix_schedule_override_sections_schedule_override_id",
        table_name="schedule_override_sections",
    )
    op.drop_index(
        "ix_schedule_override_sections_college_id",
        table_name="schedule_override_sections",
    )
    op.drop_table("schedule_override_sections")
