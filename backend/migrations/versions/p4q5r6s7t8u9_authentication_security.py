"""Account lockout, hashed recovery challenges, session revocation and throttles."""
from alembic import op
import sqlalchemy as sa

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("locked_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_failed_login_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reset_token_hash", sa.String(64)))
        batch.add_column(sa.Column("reset_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("reset_requested_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint("uq_users_reset_token_hash", ["reset_token_hash"])
    op.create_table("auth_rate_limits", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("count", sa.Integer(), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])


def downgrade():
    op.drop_table("auth_rate_limits")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_reset_token_hash", type_="unique")
        for name in ["reset_requested_at", "reset_expires_at", "reset_token_hash", "session_version",
                     "last_failed_login_at", "locked_at", "is_locked", "failed_login_attempts"]:
            batch.drop_column(name)
