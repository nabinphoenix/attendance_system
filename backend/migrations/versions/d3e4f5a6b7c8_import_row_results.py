"""store row-level import results

Revision ID: d3e4f5a6b7c8
Revises: d2e3f4a5b6c7
"""

from alembic import op
import sqlalchemy as sa


revision = "d3e4f5a6b7c8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("results_json", sa.Text(), nullable=True, server_default="[]"))


def downgrade() -> None:
    op.drop_column("import_jobs", "results_json")
