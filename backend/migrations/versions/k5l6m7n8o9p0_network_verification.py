"""add campus network verification signals to attendance"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k5l6m7n8o9p0"
down_revision = "j4e5f6g7h8i9"
branch_labels = None
depends_on = None


CIDR_TYPE = postgresql.CIDR().with_variant(sa.String(64), "sqlite")
INET_TYPE = postgresql.INET().with_variant(sa.String(45), "sqlite")


def upgrade():
    op.add_column("colleges", sa.Column("ip_policy", sa.String(10), server_default="flag", nullable=False))
    op.create_check_constraint("ck_colleges_ip_policy", "colleges", "ip_policy IN ('off', 'flag')")
    op.create_table(
        "campus_networks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("cidr", CIDR_TYPE, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campus_networks_college_id", "campus_networks", ["college_id"])
    op.create_index("ix_campus_networks_college_active", "campus_networks", ["college_id", "is_active"])
    op.add_column("class_sessions", sa.Column("teacher_ip", INET_TYPE, nullable=True))
    op.add_column("class_sessions", sa.Column("teacher_ip_status", sa.String(20), server_default="unknown", nullable=False))
    op.add_column("check_in_attempts", sa.Column("client_ip", INET_TYPE, nullable=True))
    op.add_column("check_in_attempts", sa.Column("ip_status", sa.String(20), server_default="unknown", nullable=False))
    op.add_column("check_in_attempts", sa.Column("confirm_client_ip", INET_TYPE, nullable=True))
    op.add_column("check_in_attempts", sa.Column("confirm_ip_status", sa.String(20), nullable=True))
    op.add_column("attendance_records", sa.Column("ip_status", sa.String(20), server_default="unknown", nullable=False))
    op.add_column("attendance_records", sa.Column("network_method", sa.String(20), server_default="public_ip", nullable=False))


def downgrade():
    op.drop_column("attendance_records", "network_method")
    op.drop_column("attendance_records", "ip_status")
    op.drop_column("check_in_attempts", "confirm_ip_status")
    op.drop_column("check_in_attempts", "confirm_client_ip")
    op.drop_column("check_in_attempts", "ip_status")
    op.drop_column("check_in_attempts", "client_ip")
    op.drop_column("class_sessions", "teacher_ip_status")
    op.drop_column("class_sessions", "teacher_ip")
    op.drop_index("ix_campus_networks_college_active", table_name="campus_networks")
    op.drop_index("ix_campus_networks_college_id", table_name="campus_networks")
    op.drop_table("campus_networks")
    op.drop_constraint("ck_colleges_ip_policy", "colleges", type="check")
    op.drop_column("colleges", "ip_policy")