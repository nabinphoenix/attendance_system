"""module offering foundation

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def _backfill_canonical_routines(connection):
    """Link only routines whose module, intake, batch, and sections agree."""

    routines = connection.execute(
        sa.text(
            """
            SELECT r.id, r.module_id, r.intake_id, r.semester_number, r.section_id,
                   m.semester_number AS module_semester, i.program_id AS intake_program_id
            FROM routine_entries r
            LEFT JOIN modules m ON m.id = r.module_id
            LEFT JOIN intakes i ON i.id = r.intake_id
            WHERE r.module_offering_id IS NULL
            ORDER BY r.id
            """
        )
    ).mappings()
    linked = 0
    unresolved = 0

    for routine in routines:
        section_ids = {routine["section_id"]}
        section_ids.update(
            connection.execute(
                sa.text("SELECT section_id FROM routine_entry_sections WHERE routine_entry_id = :routine_id"),
                {"routine_id": routine["id"]},
            ).scalars()
        )
        sections = []
        for section_id in section_ids:
            section = connection.execute(
                sa.text(
                    """
                    SELECT s.id, s.batch_id, s.intake_id, s.semester_number,
                           b.program_id AS batch_program_id
                    FROM sections s
                    LEFT JOIN batches b ON b.id = s.batch_id
                    WHERE s.id = :section_id
                    """
                ),
                {"section_id": section_id},
            ).mappings().first()
            if section is None:
                sections = []
                break
            sections.append(section)

        batch_ids = {section["batch_id"] for section in sections}
        valid = (
            routine["module_semester"] is not None
            and routine["intake_program_id"] is not None
            and bool(sections)
            and len(batch_ids) == 1
            and routine["module_semester"] == routine["semester_number"]
            and all(section["batch_program_id"] == routine["intake_program_id"] for section in sections)
            and all(section["intake_id"] in (None, routine["intake_id"]) for section in sections)
            and all(section["semester_number"] in (None, routine["semester_number"]) for section in sections)
        )
        if not valid:
            unresolved += 1
            print(f"ModuleOffering backfill left routine_entries.id={routine['id']} unresolved")
            continue

        batch_id = batch_ids.pop()
        offering_id = connection.execute(
            sa.text(
                """
                SELECT id FROM module_offerings
                WHERE academic_module_id = :module_id AND intake_id = :intake_id
                  AND batch_id = :batch_id AND semester_number = :semester_number
                """
            ),
            {**routine, "batch_id": batch_id},
        ).scalar()
        if offering_id is None:
            offering_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO module_offerings
                        (academic_module_id, intake_id, batch_id, semester_number, is_active)
                    VALUES (:module_id, :intake_id, :batch_id, :semester_number, true)
                    RETURNING id
                    """
                ),
                {**routine, "batch_id": batch_id},
            ).scalar_one()

        for section in sections:
            exists = connection.execute(
                sa.text(
                    """
                    SELECT 1 FROM module_offering_sections
                    WHERE module_offering_id = :offering_id AND section_id = :section_id
                    """
                ),
                {"offering_id": offering_id, "section_id": section["id"]},
            ).scalar()
            if not exists:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO module_offering_sections (module_offering_id, section_id)
                        VALUES (:offering_id, :section_id)
                        """
                    ),
                    {"offering_id": offering_id, "section_id": section["id"]},
                )
        connection.execute(
            sa.text("UPDATE routine_entries SET module_offering_id = :offering_id WHERE id = :routine_id"),
            {"offering_id": offering_id, "routine_id": routine["id"]},
        )
        linked += 1

    print(f"ModuleOffering backfill complete: linked={linked}, unresolved={unresolved}")


def upgrade():
    op.create_table(
        "module_offerings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("academic_module_id", sa.Integer(), nullable=False),
        sa.Column("intake_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("semester_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["academic_module_id"], ["modules.id"]),
        sa.ForeignKeyConstraint(["intake_id"], ["intakes.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("academic_module_id", "intake_id", "batch_id", "semester_number", name="uq_module_offering_context"),
    )
    op.create_index("ix_module_offerings_academic_module_id", "module_offerings", ["academic_module_id"])
    op.create_index("ix_module_offerings_intake_id", "module_offerings", ["intake_id"])
    op.create_index("ix_module_offerings_batch_id", "module_offerings", ["batch_id"])
    op.create_table(
        "module_offering_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_offering_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["module_offering_id"], ["module_offerings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_offering_id", "section_id", name="uq_module_offering_section"),
    )
    op.create_index("ix_module_offering_sections_section_id", "module_offering_sections", ["section_id"])
    with op.batch_alter_table("routine_entries") as batch_op:
        batch_op.add_column(sa.Column("module_offering_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_routine_entries_module_offering", "module_offerings", ["module_offering_id"], ["id"]
        )
    op.create_index("ix_routine_entries_module_offering_id", "routine_entries", ["module_offering_id"])
    _backfill_canonical_routines(op.get_bind())


def downgrade():
    op.drop_index("ix_routine_entries_module_offering_id", table_name="routine_entries")
    with op.batch_alter_table("routine_entries") as batch_op:
        batch_op.drop_constraint("fk_routine_entries_module_offering", type_="foreignkey")
        batch_op.drop_column("module_offering_id")
    op.drop_index("ix_module_offering_sections_section_id", table_name="module_offering_sections")
    op.drop_table("module_offering_sections")
    op.drop_index("ix_module_offerings_batch_id", table_name="module_offerings")
    op.drop_index("ix_module_offerings_intake_id", table_name="module_offerings")
    op.drop_index("ix_module_offerings_academic_module_id", table_name="module_offerings")
    op.drop_table("module_offerings")
