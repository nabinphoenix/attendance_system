"""session teacher geofence

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("class_sessions") as batch:
        batch.add_column(sa.Column("geofence_latitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("geofence_longitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("geofence_radius_meters", sa.Float(), nullable=True))
        batch.add_column(sa.Column("teacher_location_accuracy_meters", sa.Float(), nullable=True))
        batch.add_column(sa.Column("geofence_captured_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("class_sessions") as batch:
        batch.drop_column("geofence_captured_at")
        batch.drop_column("teacher_location_accuracy_meters")
        batch.drop_column("geofence_radius_meters")
        batch.drop_column("geofence_longitude")
        batch.drop_column("geofence_latitude")
