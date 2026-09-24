"""add college-scoped Google Workspace connections and resources

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
"""

from alembic import op
import sqlalchemy as sa


revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_oauth_attempts",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("state_hash"),
    )
    op.create_index("ix_google_oauth_attempts_user_id", "google_oauth_attempts", ["user_id"])
    op.create_index("ix_google_oauth_attempts_college_id", "google_oauth_attempts", ["college_id"])
    op.create_index("ix_google_oauth_attempts_expires_at", "google_oauth_attempts", ["expires_at"])
    op.create_table(
        "google_workspace_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connected_by_id", sa.Integer(), nullable=False),
        sa.Column("google_email", sa.String(length=255), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("college_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"]),
        sa.ForeignKeyConstraint(["connected_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("college_id", name="uq_google_workspace_connections_college"),
    )
    op.create_index("ix_google_workspace_connections_college_id", "google_workspace_connections", ["college_id"])
    op.create_table(
        "google_workspace_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("google_resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["google_workspace_connections.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("college_id", "google_resource_id", name="uq_google_workspace_resource_college_id"),
    )
    op.create_index("ix_google_workspace_resources_college_id", "google_workspace_resources", ["college_id"])


def downgrade() -> None:
    op.drop_index("ix_google_workspace_resources_college_id", table_name="google_workspace_resources")
    op.drop_table("google_workspace_resources")
    op.drop_index("ix_google_workspace_connections_college_id", table_name="google_workspace_connections")
    op.drop_table("google_workspace_connections")
    op.drop_index("ix_google_oauth_attempts_expires_at", table_name="google_oauth_attempts")
    op.drop_index("ix_google_oauth_attempts_college_id", table_name="google_oauth_attempts")
    op.drop_index("ix_google_oauth_attempts_user_id", table_name="google_oauth_attempts")
    op.drop_table("google_oauth_attempts")
