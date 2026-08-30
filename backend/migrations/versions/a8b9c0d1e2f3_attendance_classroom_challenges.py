"""add classroom QR challenges and pending code verification

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_session_id", sa.Integer(), sa.ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qr_version", sa.Integer(), nullable=False),
        sa.Column("qr_nonce", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("class_session_id", "qr_version", name="uq_attendance_challenge_session_qr_version"),
    )
    op.create_index("ix_attendance_challenges_session_active", "attendance_challenges", ["class_session_id", "revoked_at", "expires_at"])
    op.create_table(
        "pending_attendance_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("class_session_id", sa.Integer(), sa.ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attendance_challenge_id", sa.Integer(), sa.ForeignKey("attendance_challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qr_version", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("allowed_radius_meters", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_pending_attendance_verification_token"),
    )
    op.create_index("ix_pending_attendance_verification_student", "pending_attendance_verifications", ["student_id", "class_session_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pending_attendance_verification_student", table_name="pending_attendance_verifications")
    op.drop_table("pending_attendance_verifications")
    op.drop_index("ix_attendance_challenges_session_active", table_name="attendance_challenges")
    op.drop_table("attendance_challenges")
