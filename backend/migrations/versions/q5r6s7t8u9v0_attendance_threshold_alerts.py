"""Track idempotent subject-wise attendance threshold alerts.

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
"""

from alembic import op
import sqlalchemy as sa


revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    alert_status = sa.Enum("active", "resolved", name="attendancethresholdalertstatus")
    op.create_table(
        "attendance_threshold_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("module_offering_id", sa.Integer(), sa.ForeignKey("module_offerings.id"), nullable=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id"), nullable=True),
        sa.Column("cohort_semester_id", sa.Integer(), sa.ForeignKey("cohort_semesters.id"), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("percentage_at_trigger", sa.Float(), nullable=False),
        sa.Column("attended_sessions", sa.Integer(), nullable=False),
        sa.Column("eligible_sessions", sa.Integer(), nullable=False),
        sa.Column("status", alert_status, nullable=False, server_default="active"),
        sa.Column("first_triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("email_queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "module_offering_id IS NOT NULL OR subject_id IS NOT NULL",
            name="ck_attendance_alert_scope",
        ),
    )
    op.create_index(
        "ix_attendance_threshold_alerts_college_id",
        "attendance_threshold_alerts",
        ["college_id"],
    )
    op.create_index(
        "ix_attendance_alert_student_context",
        "attendance_threshold_alerts",
        ["student_id", "cohort_semester_id", "status"],
    )
    op.create_index(
        "uq_active_attendance_alert_module",
        "attendance_threshold_alerts",
        ["student_id", "module_offering_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND module_offering_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'active' AND module_offering_id IS NOT NULL"),
    )
    op.create_index(
        "uq_active_attendance_alert_subject",
        "attendance_threshold_alerts",
        ["student_id", "subject_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND subject_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'active' AND subject_id IS NOT NULL"),
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("actor_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("failure_reason", sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            "fk_notifications_actor_id_users", "users", ["actor_id"], ["id"]
        )
    op.create_index(
        "ix_notifications_retry",
        "notifications",
        ["status", "next_attempt_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            'CREATE TRIGGER college_owner_immutable BEFORE UPDATE ON "attendance_threshold_alerts" '
            "FOR EACH ROW EXECUTE FUNCTION enforce_college_reference()"
        )
        for column, table, mode in (
            ("student_id", "students", "relation"),
            ("module_offering_id", "module_offerings", "relation"),
            ("subject_id", "subjects", "relation"),
            ("cohort_semester_id", "cohort_semesters", "relation"),
            ("notification_id", "notifications", "relation"),
        ):
            op.execute(
                "CREATE TRIGGER college_ref_{column} BEFORE INSERT OR UPDATE ON "
                "attendance_threshold_alerts FOR EACH ROW EXECUTE FUNCTION "
                "enforce_college_reference('{table}', '{column}', '{mode}')".format(
                    column=column, table=table, mode=mode
                )
            )
        op.execute(
            "CREATE TRIGGER college_ref_actor_id BEFORE INSERT OR UPDATE ON notifications "
            "FOR EACH ROW EXECUTE FUNCTION "
            "enforce_college_reference('users', 'actor_id', 'actor')"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS college_ref_actor_id ON notifications")
    op.drop_index("ix_notifications_retry", table_name="notifications")
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("fk_notifications_actor_id_users", type_="foreignkey")
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("delivery_attempts")
        batch_op.drop_column("actor_id")
    op.drop_index("uq_active_attendance_alert_subject", table_name="attendance_threshold_alerts")
    op.drop_index("uq_active_attendance_alert_module", table_name="attendance_threshold_alerts")
    op.drop_index("ix_attendance_alert_student_context", table_name="attendance_threshold_alerts")
    op.drop_index("ix_attendance_threshold_alerts_college_id", table_name="attendance_threshold_alerts")
    op.drop_table("attendance_threshold_alerts")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="attendancethresholdalertstatus").drop(op.get_bind(), checkfirst=True)
