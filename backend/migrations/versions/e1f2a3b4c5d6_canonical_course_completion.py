"""connect course completion to canonical routine delivery

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("course_plans", sa.Column("module_offering_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_course_plans_module_offering",
        "course_plans",
        "module_offerings",
        ["module_offering_id"],
        ["id"],
    )
    op.alter_column("course_plans", "subject_id", existing_type=sa.Integer(), nullable=True)
    op.create_unique_constraint(
        "uq_course_plan_offering_batch",
        "course_plans",
        ["module_offering_id", "batch_id"],
    )
    op.create_check_constraint(
        "ck_course_plan_source",
        "course_plans",
        "(subject_id IS NOT NULL) <> (module_offering_id IS NOT NULL)",
    )

    op.add_column("makeup_suggestions", sa.Column("routine_entry_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_makeup_suggestions_routine_entry",
        "makeup_suggestions",
        "routine_entries",
        ["routine_entry_id"],
        ["id"],
    )
    op.alter_column("makeup_suggestions", "timetable_entry_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_makeup_suggestion_source",
        "makeup_suggestions",
        "(timetable_entry_id IS NOT NULL) <> (routine_entry_id IS NOT NULL)",
    )

    op.add_column(
        "schedule_overrides",
        sa.Column("is_makeup", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # The original migration created both an unnamed unique constraint and a
    # non-unique index. The ORM correctly models this as one unique index.
    op.drop_constraint("student_invitations_token_hash_key", "student_invitations", type_="unique")
    op.drop_index("ix_student_invitations_token_hash", table_name="student_invitations")
    op.create_index(
        "ix_student_invitations_token_hash",
        "student_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_student_invitations_token_hash", table_name="student_invitations")
    op.create_unique_constraint(
        "student_invitations_token_hash_key",
        "student_invitations",
        ["token_hash"],
    )
    op.create_index("ix_student_invitations_token_hash", "student_invitations", ["token_hash"])

    op.drop_column("schedule_overrides", "is_makeup")
    op.drop_constraint("ck_makeup_suggestion_source", "makeup_suggestions", type_="check")
    op.drop_constraint("fk_makeup_suggestions_routine_entry", "makeup_suggestions", type_="foreignkey")
    op.drop_column("makeup_suggestions", "routine_entry_id")
    op.alter_column("makeup_suggestions", "timetable_entry_id", existing_type=sa.Integer(), nullable=False)

    op.drop_constraint("ck_course_plan_source", "course_plans", type_="check")
    op.drop_constraint("uq_course_plan_offering_batch", "course_plans", type_="unique")
    op.drop_constraint("fk_course_plans_module_offering", "course_plans", type_="foreignkey")
    op.drop_column("course_plans", "module_offering_id")
    op.alter_column("course_plans", "subject_id", existing_type=sa.Integer(), nullable=False)
