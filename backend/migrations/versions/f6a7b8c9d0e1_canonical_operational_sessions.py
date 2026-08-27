"""canonical routine operational sessions

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from alembic import op
import sqlalchemy as sa
revision="f6a7b8c9d0e1";down_revision="e5f6a7b8c9d0";branch_labels=None;depends_on=None
def upgrade():
    with op.batch_alter_table("class_sessions") as b:
        b.alter_column("timetable_entry_id",existing_type=sa.Integer(),nullable=True)
        b.add_column(sa.Column("routine_entry_id",sa.Integer(),nullable=True))
        b.create_foreign_key("fk_class_sessions_routine_entry","routine_entries",["routine_entry_id"],["id"])
    op.create_index("ix_class_sessions_routine_entry_id","class_sessions",["routine_entry_id"])
    with op.batch_alter_table("schedule_overrides") as b:
        b.alter_column("timetable_entry_id",existing_type=sa.Integer(),nullable=True)
        b.add_column(sa.Column("routine_entry_id",sa.Integer(),nullable=True))
        b.create_foreign_key("fk_schedule_overrides_routine_entry","routine_entries",["routine_entry_id"],["id"])
    op.create_index("ix_schedule_overrides_routine_entry_id","schedule_overrides",["routine_entry_id"])
    op.create_check_constraint("ck_class_sessions_schedule_source","class_sessions","routine_entry_id IS NOT NULL OR timetable_entry_id IS NOT NULL")
    op.create_check_constraint("ck_schedule_overrides_schedule_source","schedule_overrides","routine_entry_id IS NOT NULL OR timetable_entry_id IS NOT NULL")
def downgrade():
    op.drop_constraint("ck_schedule_overrides_schedule_source","schedule_overrides",type_="check");op.drop_index("ix_schedule_overrides_routine_entry_id",table_name="schedule_overrides")
    with op.batch_alter_table("schedule_overrides") as b:b.drop_constraint("fk_schedule_overrides_routine_entry",type_="foreignkey");b.drop_column("routine_entry_id")
    op.drop_constraint("ck_class_sessions_schedule_source","class_sessions",type_="check");op.drop_index("ix_class_sessions_routine_entry_id",table_name="class_sessions")
    with op.batch_alter_table("class_sessions") as b:b.drop_constraint("fk_class_sessions_routine_entry",type_="foreignkey");b.drop_column("routine_entry_id")
