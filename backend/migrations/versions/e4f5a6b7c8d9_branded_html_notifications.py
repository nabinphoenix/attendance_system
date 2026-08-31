"""store branded HTML notification content

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from alembic import op
import sqlalchemy as sa


revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("html_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "html_body")
