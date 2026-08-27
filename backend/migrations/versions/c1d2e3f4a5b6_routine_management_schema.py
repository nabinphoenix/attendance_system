"""routine management schema

Revision ID: c1d2e3f4a5b6
Revises: b9ae91e2c103
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b9ae91e2c103"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("intakes",sa.Column("id",sa.Integer,primary_key=True),sa.Column("name",sa.String(100),nullable=False,unique=True),sa.Column("code",sa.String(50),nullable=False,unique=True),sa.Column("start_date",sa.Date,nullable=False),sa.Column("program_id",sa.Integer,sa.ForeignKey("programs.id"),nullable=False))
    op.create_table("blocks",sa.Column("id",sa.Integer,primary_key=True),sa.Column("name",sa.String(100),nullable=False,unique=True))
    op.create_table("modules",sa.Column("id",sa.Integer,primary_key=True),sa.Column("code",sa.String(30),nullable=False,unique=True),sa.Column("title",sa.String(200),nullable=False),sa.Column("credits",sa.Integer,nullable=False),sa.Column("semester_number",sa.Integer,nullable=False))
    op.create_table("class_types",sa.Column("id",sa.Integer,primary_key=True),sa.Column("name",sa.String(50),nullable=False,unique=True))
    op.bulk_insert(sa.table("class_types", sa.column("name", sa.String)), [
        {"name": "Lecture"}, {"name": "Tutorial"}, {"name": "Practical"},
    ])
    op.create_table("time_slots",sa.Column("id",sa.Integer,primary_key=True),sa.Column("start_time",sa.Time,nullable=False),sa.Column("end_time",sa.Time,nullable=False),sa.Column("duration_label",sa.String(30),nullable=False),sa.UniqueConstraint("start_time","end_time",name="uq_time_slot_range"))
    op.create_table("rooms",sa.Column("id",sa.Integer,primary_key=True),sa.Column("block_id",sa.Integer,sa.ForeignKey("blocks.id"),nullable=False),sa.Column("name",sa.String(120),nullable=False),sa.Column("room_type",sa.String(30),nullable=False),sa.Column("capacity",sa.Integer,nullable=False),sa.UniqueConstraint("block_id","name",name="uq_room_block_name"))
    with op.batch_alter_table("sections") as batch:
        batch.add_column(sa.Column("intake_id",sa.Integer,nullable=True))
        batch.add_column(sa.Column("semester_number",sa.Integer,nullable=True))
        batch.add_column(sa.Column("combined_with",sa.String(100),nullable=True))
        batch.create_foreign_key("fk_sections_intake_id_intakes","intakes",["intake_id"],["id"])
    op.create_table("routine_entries",sa.Column("id",sa.Integer,primary_key=True),sa.Column("intake_id",sa.Integer,sa.ForeignKey("intakes.id"),nullable=False),sa.Column("semester_number",sa.Integer,nullable=False),sa.Column("section_id",sa.Integer,sa.ForeignKey("sections.id"),nullable=False),sa.Column("module_id",sa.Integer,sa.ForeignKey("modules.id"),nullable=False),sa.Column("class_type_id",sa.Integer,sa.ForeignKey("class_types.id"),nullable=False),sa.Column("teacher_id",sa.Integer,sa.ForeignKey("teachers.id"),nullable=False),sa.Column("room_id",sa.Integer,sa.ForeignKey("rooms.id"),nullable=False),sa.Column("day_of_week",sa.Integer,nullable=False),sa.Column("time_slot_id",sa.Integer,sa.ForeignKey("time_slots.id"),nullable=False))

def downgrade() -> None:
    op.drop_table("routine_entries")
    with op.batch_alter_table("sections") as batch:
        batch.drop_constraint("fk_sections_intake_id_intakes",type_="foreignkey")
        batch.drop_column("combined_with");batch.drop_column("semester_number");batch.drop_column("intake_id")
    op.drop_table("rooms");op.drop_table("time_slots");op.drop_table("class_types");op.drop_table("modules");op.drop_table("blocks");op.drop_table("intakes")
