"""backfill cohort-wide module offering section membership

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from alembic import op


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Module offerings describe a cohort (intake, batch, semester), not a
    # manually selected subset of its sections. Preserve the legacy nullable
    # section context rule while adding every missing cohort membership.
    op.execute(
        """
        INSERT INTO module_offering_sections (module_offering_id, section_id)
        SELECT offering.id, section.id
        FROM module_offerings AS offering
        JOIN sections AS section
          ON section.batch_id = offering.batch_id
         AND (section.intake_id = offering.intake_id OR section.intake_id IS NULL)
         AND (section.semester_number = offering.semester_number OR section.semester_number IS NULL)
        WHERE NOT EXISTS (
          SELECT 1
          FROM module_offering_sections AS membership
          WHERE membership.module_offering_id = offering.id
            AND membership.section_id = section.id
        )
        """
    )


def downgrade() -> None:
    # This is a data correction. A safe downgrade cannot distinguish a former
    # manually selected relationship from one added by the upgrade.
    pass
