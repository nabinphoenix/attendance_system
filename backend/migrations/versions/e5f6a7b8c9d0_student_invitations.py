"""student invitations and unregistered student profiles

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("name", sa.String(150), nullable=True))
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
    op.create_index("ix_students_email", "students", ["email"])
    op.execute("UPDATE students SET name = users.name, email = users.email FROM users WHERE students.user_id = users.id")
    op.create_table("student_invitations", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("student_id",sa.Integer(),sa.ForeignKey("students.id",ondelete="CASCADE"),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("status",sa.Enum("SENT","ACTIVATED","REVOKED",name="invitationstatus"),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("used_at",sa.DateTime(timezone=True),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False))
    op.create_index("ix_student_invitations_token_hash","student_invitations",["token_hash"])

def downgrade() -> None:
    op.drop_index("ix_student_invitations_token_hash",table_name="student_invitations")
    op.drop_table("student_invitations")
    op.drop_index("ix_students_email",table_name="students")
    with op.batch_alter_table("students") as batch:
        batch.drop_column("email");batch.drop_column("name");batch.alter_column("user_id",existing_type=sa.Integer(),nullable=False)
