"""dynamic qr geofence evidence

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa

revision="b8c9d0e1f2a3";down_revision="a7b8c9d0e1f2";branch_labels=None;depends_on=None

def upgrade():
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("latitude",sa.Float(),nullable=True));batch.add_column(sa.Column("longitude",sa.Float(),nullable=True));batch.add_column(sa.Column("geofence_radius_meters",sa.Float(),nullable=True))
    with op.batch_alter_table("class_sessions") as batch:
        batch.add_column(sa.Column("qr_version",sa.Integer(),nullable=False,server_default="0"));batch.add_column(sa.Column("qr_nonce",sa.String(length=64),nullable=True));batch.add_column(sa.Column("qr_issued_at",sa.DateTime(timezone=True),nullable=True))
    attempt_status=sa.Enum("ACCEPTED","PENDING","CONFIRMED","REJECTED",name="checkinattemptstatus")
    op.create_table("check_in_attempts",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("class_session_id",sa.Integer(),sa.ForeignKey("class_sessions.id",ondelete="CASCADE"),nullable=False),sa.Column("student_id",sa.Integer(),sa.ForeignKey("students.id"),nullable=False),sa.Column("status",attempt_status,nullable=False),sa.Column("failure_reason",sa.String(50),nullable=True),sa.Column("qr_version",sa.Integer(),nullable=True),sa.Column("latitude",sa.Float(),nullable=True),sa.Column("longitude",sa.Float(),nullable=True),sa.Column("accuracy_meters",sa.Float(),nullable=True),sa.Column("distance_meters",sa.Float(),nullable=True),sa.Column("allowed_radius_meters",sa.Float(),nullable=True),sa.Column("geofence_pass",sa.Boolean(),nullable=True),sa.Column("reviewed_by",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("reviewed_at",sa.DateTime(timezone=True),nullable=True),sa.Column("decision_reason",sa.Text(),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_check_in_attempt_session_status","check_in_attempts",["class_session_id","status"])

def downgrade():
    op.drop_index("ix_check_in_attempt_session_status",table_name="check_in_attempts");op.drop_table("check_in_attempts")
    sa.Enum(name="checkinattemptstatus").drop(op.get_bind(),checkfirst=True)
    with op.batch_alter_table("class_sessions") as batch:batch.drop_column("qr_issued_at");batch.drop_column("qr_nonce");batch.drop_column("qr_version")
    with op.batch_alter_table("rooms") as batch:batch.drop_column("geofence_radius_meters");batch.drop_column("longitude");batch.drop_column("latitude")
