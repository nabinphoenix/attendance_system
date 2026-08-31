"""store user profile photos in PostgreSQL

Revision ID: d2e3f4a5b6c7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e3f4a5b6c7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_data")
