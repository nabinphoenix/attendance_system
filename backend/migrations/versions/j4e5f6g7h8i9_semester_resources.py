"""Semester academic calendars and mid-semester teacher feedback."""
from alembic import op
import sqlalchemy as sa

revision = "j4e5f6g7h8i9"
down_revision = "i3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "academic_calendars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=False),
        sa.Column("cohort_semester_id", sa.Integer(), sa.ForeignKey("cohort_semesters.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("pdf_data", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cohort_semester_id", name="uq_academic_calendar_semester"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_calendar_size"),
    )
    op.create_table(
        "teacher_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=False),
        sa.Column("cohort_semester_id", sa.Integer(), sa.ForeignKey("cohort_semesters.id"), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("form_url", sa.String(2048), nullable=False),
        sa.Column("opens_on", sa.Date(), nullable=False),
        sa.Column("closes_on", sa.Date(), nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("cohort_semester_id", "teacher_id", name="uq_teacher_feedback_semester"),
        sa.CheckConstraint("opens_on <= closes_on", name="ck_teacher_feedback_dates"),
    )
    for table in ("academic_calendars", "teacher_feedback"):
        op.create_index(f"ix_{table}_college_id", table, ["college_id"])
    # Retain the database-level college reference protections used by the
    # existing multi-college migration, including global super-admin actors.
    if op.get_bind().dialect.name == "postgresql":
        for table, references in {
            "academic_calendars": [("cohort_semester_id", "cohort_semesters", "relation"), ("uploaded_by", "users", "actor")],
            "teacher_feedback": [("cohort_semester_id", "cohort_semesters", "relation"), ("teacher_id", "teachers", "relation"), ("created_by", "users", "actor")],
        }.items():
            op.execute(f'CREATE TRIGGER college_owner_immutable BEFORE UPDATE ON "{table}" FOR EACH ROW EXECUTE FUNCTION enforce_college_reference()')
            for column, target, mode in references:
                op.execute(f"CREATE TRIGGER college_ref_{column} BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION enforce_college_reference('{target}', '{column}', '{mode}')")


def downgrade():
    op.drop_table("teacher_feedback")
    op.drop_table("academic_calendars")
