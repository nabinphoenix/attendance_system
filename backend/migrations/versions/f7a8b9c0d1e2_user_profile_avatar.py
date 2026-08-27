"""add user profile avatar storage key

Revision ID: f7a8b9c0d1e2
Revises: f2a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
