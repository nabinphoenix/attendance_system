"""Keep BSc.IT catalog modules independent from a permanent semester."""

from alembic import op
import sqlalchemy as sa


revision = "m1n2o3p4q5r6"
down_revision = "l0m1n2o3p4q5"
branch_labels = None
depends_on = None


CATALOG_CODES = (
    "AQ010-3-1-MCFC", "CT018-3-1-ICP", "CT026-3-1-SAAD", "CT042-3-1-IDB",
    "CT043-3-1-IN", "NP-LBEF-001", "CT049-3-1-OSCA", "CT053-3-1-FDD",
    "CT108-3-1-PYP", "CT109-3-1-DGTIN", "ERA002-3-1-IACD", "NP-LBEF-002",
    "NP-LBEF-003", "AQ077-3-2-PSMOD", "CT038-3-2-OODJ", "CT046-3-2-SDM",
    "CT090-3-2-MWT", "CT106-3-2-SNA", "CT127-3-2-PFDA", "MPU3272-WPCS",
    "BM006-3-2-CRI", "CT026-3-2-HCI", "CT050-3-2-WAPP", "CT098-3-2-RMCT",
    "CT104-3-2-IBPSES", "CT109-3-2-DCI", "MPU3362-EET", "CT012-3-3-CSM",
    "CT024-3-3-DCOMS", "CT050-3-3-PRMGT", "CT052-3-3-IIT", "CT081-3-3-MWM",
    "CT097-3-3-CSVC", "IT001-4-3-IE2", "BM019-3-3", "BM050-3-3",
    "CT004-3-3", "CT049-6-3", "CT071-3-3",
)


def upgrade():
    conn = op.get_bind()
    modules = sa.table(
        "modules",
        sa.column("college_id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("semester_number", sa.Integer()),
    )
    programs = sa.table(
        "programs",
        sa.column("college_id", sa.Integer()),
        sa.column("name", sa.String()),
    )
    college_ids = sa.select(programs.c.college_id).where(
        sa.func.lower(programs.c.name) == "bsc.it"
    )
    conn.execute(
        modules.update()
        .where(
            modules.c.college_id.in_(college_ids),
            modules.c.code.in_(CATALOG_CODES),
        )
        .values(semester_number=None)
    )


def downgrade():
    # The previous values were legacy metadata and cannot be reconstructed
    # safely; module offerings remain the authoritative historical record.
    pass
