"""guarded AI assistant approvals

Revision ID: h2c3d4e5f6g7
Revises: g1b2c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa


revision = "h2c3d4e5f6g7"
down_revision = "g1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_agent_approvals_actor_id", "agent_approvals", ["actor_id"])
    op.create_index("ix_agent_approvals_expires_at", "agent_approvals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_approvals_expires_at", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_actor_id", table_name="agent_approvals")
    op.drop_table("agent_approvals")
