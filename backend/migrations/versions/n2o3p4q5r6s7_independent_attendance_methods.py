"""record independent QR and attendance-code check-ins"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE attendancemethod ADD VALUE IF NOT EXISTS 'QR'")
        op.execute("ALTER TYPE attendancemethod ADD VALUE IF NOT EXISTS 'CODE'")
        method_type = postgresql.ENUM(name="attendancemethod", create_type=False)
    else:
        method_type = sa.Enum("QR_GEOFENCE", "FINALIZATION", "MANUAL", "QR", "CODE", name="attendancemethod")
    op.add_column(
        "pending_attendance_verifications",
        sa.Column("attendance_method", method_type, nullable=False, server_default="QR_GEOFENCE"),
    )


def downgrade():
    # Convert new records to legacy values before an older app reads them.
    op.execute("UPDATE attendance_records SET method = 'QR_GEOFENCE' WHERE method = 'QR'")
    op.execute("UPDATE attendance_records SET method = 'MANUAL' WHERE method = 'CODE'")
    op.drop_column("pending_attendance_verifications", "attendance_method")
    # PostgreSQL enum values remain; removing them requires replacing the type.
