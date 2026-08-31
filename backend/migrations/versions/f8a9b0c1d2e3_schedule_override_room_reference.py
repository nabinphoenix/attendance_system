"""add a room reference to canonical schedule overrides

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
"""
from alembic import op
import sqlalchemy as sa


revision = "f8a9b0c1d2e3"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("schedule_overrides") as batch:
        batch.add_column(sa.Column("new_room_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_schedule_overrides_new_room_id_rooms",
            "rooms",
            ["new_room_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("schedule_overrides") as batch:
        batch.drop_constraint("fk_schedule_overrides_new_room_id_rooms", type_="foreignkey")
        batch.drop_column("new_room_id")
