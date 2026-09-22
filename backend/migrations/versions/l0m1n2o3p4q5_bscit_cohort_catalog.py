"""Make BSc.IT cohort semesters authoritative and seed its course catalog."""

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "l0m1n2o3p4q5"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


CATALOG = (
    ("AQ010-3-1-MCFC", "Mathematical Concept For Computing", 3),
    ("CT018-3-1-ICP", "Introduction to C Programming", 3),
    ("CT026-3-1-SAAD", "Systems Analysis and Design", 3),
    ("CT042-3-1-IDB", "Introduction to Databases", 3),
    ("CT043-3-1-IN", "Introduction to Networking", 3),
    ("NP-LBEF-001", "Nepal Parichaya", 3),
    ("CT049-3-1-OSCA", "Operating Systems and Computer Architecture", 3),
    ("CT053-3-1-FDD", "Fundamentals of Web Design and Development", 3),
    ("CT108-3-1-PYP", "Programming with Python", 3),
    ("CT109-3-1-DGTIN", "Digital Thinking and Innovation", 3),
    ("ERA002-3-1-IACD", "Intercultural Awareness and Cultural Diversity", 3),
    ("NP-LBEF-002", "Personality Development", 3),
    ("NP-LBEF-003", "Technical Communication", 3),
    ("AQ077-3-2-PSMOD", "Probability and Statistical Modelling", 3),
    ("CT038-3-2-OODJ", "Object Oriented Development with Java", 3),
    ("CT046-3-2-SDM", "System Development Methods", 3),
    ("CT090-3-2-MWT", "Mobile and Wireless Technology", 3),
    ("CT106-3-2-SNA", "System and Network Administration", 3),
    ("CT127-3-2-PFDA", "Programming for Data Analysis", 3),
    ("MPU3272-WPCS", "Workplace Professional Communication Skills", 3),
    ("BM006-3-2-CRI", "Creativity and Innovation", 3),
    ("CT026-3-2-HCI", "Human Computer Interaction", 3),
    ("CT050-3-2-WAPP", "Web Applications", 3),
    ("CT098-3-2-RMCT", "Research Methods for Computing and Technology", 3),
    ("CT104-3-2-IBPSES", "Integrated Business Processes with SAP ERP System", 3),
    ("CT109-3-2-DCI", "Data Centre Infrastructure", 3),
    ("MPU3362-EET", "Employee and Employment Trends", 3),
    ("CT012-3-3-CSM", "Computer System Management", 3),
    ("CT024-3-3-DCOMS", "Distributed Computer Systems", 3),
    ("CT050-3-3-PRMGT", "Project Management", 3),
    ("CT052-3-3-IIT", "Investigations in Information Technology", 3),
    ("CT081-3-3-MWM", "Mobile and Web Multimedia", 3),
    ("CT097-3-3-CSVC", "Cloud Infrastructure and Services", 3),
    ("IT001-4-3-IE2", "Internship", 4),
    ("BM019-3-3", "Entrepreneurship", 3),
    ("BM050-3-3", "Innovation Management and New Product Development", 3),
    ("CT004-3-3", "Advanced Database Systems", 3),
    ("CT049-6-3", "Final Year Project", 6),
    ("CT071-3-3", "Designing and Developing Applications on the Cloud", 3),
)


def _table(name, *columns):
    return sa.table(name, *[sa.column(column, type_) for column, type_ in columns])


def upgrade():
    with op.batch_alter_table("sections") as batch:
        batch.add_column(sa.Column("cohort_semester_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_sections_cohort_semester_id",
            "cohort_semesters",
            ["cohort_semester_id"],
            ["id"],
        )
    op.create_index("ix_sections_cohort_semester_id", "sections", ["cohort_semester_id"])

    with op.batch_alter_table("modules") as batch:
        batch.alter_column("semester_number", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("module_offerings") as batch:
        batch.add_column(
            sa.Column("inherit_all_sections", sa.Boolean(), server_default=sa.true(), nullable=False)
        )

    conn = op.get_bind()
    intakes = _table(
        "intakes",
        ("id", sa.Integer()),
        ("start_date", sa.Date()),
    )
    batches = _table("batches", ("id", sa.Integer()))
    sections = _table(
        "sections",
        ("id", sa.Integer()),
        ("intake_id", sa.Integer()),
        ("batch_id", sa.Integer()),
        ("semester_number", sa.Integer()),
        ("cohort_semester_id", sa.Integer()),
    )
    offerings = _table(
        "module_offerings",
        ("intake_id", sa.Integer()),
        ("batch_id", sa.Integer()),
        ("semester_number", sa.Integer()),
        ("cohort_semester_id", sa.Integer()),
    )
    routines = _table(
        "routine_entries",
        ("id", sa.Integer()),
        ("intake_id", sa.Integer()),
        ("semester_number", sa.Integer()),
        ("section_id", sa.Integer()),
        ("module_offering_id", sa.Integer()),
        ("cohort_semester_id", sa.Integer()),
    )
    cohorts = _table(
        "cohort_semesters",
        ("id", sa.Integer()),
        ("intake_id", sa.Integer()),
        ("batch_id", sa.Integer()),
        ("semester_number", sa.Integer()),
        ("attempt_number", sa.Integer()),
        ("start_date", sa.Date()),
        ("end_date", sa.Date()),
        ("status", sa.String()),
    )

    contexts = set()
    for table in (sections, offerings):
        contexts.update(
            (row.intake_id, row.batch_id, row.semester_number)
            for row in conn.execute(
                sa.select(table.c.intake_id, table.c.batch_id, table.c.semester_number)
                .where(
                    table.c.intake_id.is_not(None),
                    table.c.batch_id.is_not(None),
                    table.c.semester_number.is_not(None),
                )
            )
        )

    period_by_context = {}
    for intake_id, batch_id, semester_number in sorted(contexts):
        existing = conn.execute(
            sa.select(cohorts.c.id).where(
                cohorts.c.intake_id == intake_id,
                cohorts.c.batch_id == batch_id,
                cohorts.c.semester_number == semester_number,
            ).order_by(cohorts.c.attempt_number.desc(), cohorts.c.id.desc())
        ).first()
        if existing:
            period_by_context[(intake_id, batch_id, semester_number)] = existing.id
            continue
        intake_start = conn.execute(
            sa.select(intakes.c.start_date).where(intakes.c.id == intake_id)
        ).scalar_one_or_none() or date.today()
        period_id = conn.execute(
            cohorts.insert().values(
                intake_id=intake_id,
                batch_id=batch_id,
                semester_number=semester_number,
                attempt_number=1,
                start_date=intake_start,
                # Existing deployments do not store an end date for the
                # current live semester. Keep it open until an administrator
                # supplies the real academic calendar dates.
                end_date=date(9999, 12, 31),
                status="active",
            )
            .returning(cohorts.c.id)
        ).scalar_one()
        period_by_context[(intake_id, batch_id, semester_number)] = period_id

    for table in (sections, offerings):
        for context, period_id in period_by_context.items():
            intake_id, batch_id, semester_number = context
            conn.execute(
                table.update()
                .where(
                    table.c.intake_id == intake_id,
                    table.c.batch_id == batch_id,
                    table.c.semester_number == semester_number,
                    table.c.cohort_semester_id.is_(None),
                )
                .values(cohort_semester_id=period_id)
            )

    for row in conn.execute(
        sa.select(routines.c.id, routines.c.section_id, routines.c.module_offering_id)
        .where(routines.c.cohort_semester_id.is_(None))
    ):
        period_id = conn.execute(
            sa.select(sections.c.cohort_semester_id).where(sections.c.id == row.section_id)
        ).scalar_one_or_none()
        if period_id is None and row.module_offering_id is not None:
            period_id = conn.execute(
                sa.select(offerings.c.cohort_semester_id).where(
                    offerings.c.id == row.module_offering_id
                )
            ).scalar_one_or_none()
        if period_id is not None:
            conn.execute(
                routines.update().where(routines.c.id == row.id).values(
                    cohort_semester_id=period_id
                )
            )

    enrollments = _table(
        "student_enrollments",
        ("id", sa.Integer()),
        ("section_id", sa.Integer()),
        ("cohort_semester_id", sa.Integer()),
    )
    conn.execute(
        enrollments.update()
        .where(
            enrollments.c.cohort_semester_id.is_(None),
            enrollments.c.section_id == sections.c.id,
            sections.c.cohort_semester_id.is_not(None),
        )
        .values(cohort_semester_id=sections.c.cohort_semester_id)
    )

    programs = _table("programs", ("name", sa.String()), ("college_id", sa.Integer()))
    modules = _table(
        "modules",
        ("id", sa.Integer()),
        ("college_id", sa.Integer()),
        ("code", sa.String()),
        ("title", sa.String()),
        ("credits", sa.Integer()),
        ("semester_number", sa.Integer()),
    )
    college_ids = [
        row.college_id
        for row in conn.execute(
            sa.select(programs.c.college_id)
            .where(sa.func.lower(programs.c.name) == "bsc.it")
            .distinct()
        )
    ]
    for college_id in college_ids:
        for code, title, credits in CATALOG:
            existing = conn.execute(
                sa.select(modules.c.id)
                .where(modules.c.college_id == college_id, modules.c.code == code)
                .limit(1)
            ).first()
            if existing:
                conn.execute(
                    modules.update()
                    .where(modules.c.id == existing.id)
                    .values(title=title, credits=credits)
                )
            else:
                conn.execute(
                    modules.insert().values(
                        college_id=college_id,
                        code=code,
                        title=title,
                        credits=credits,
                        semester_number=None,
                    )
                )


def downgrade():
    conn = op.get_bind()
    modules = sa.table("modules", sa.column("semester_number", sa.Integer()))
    if conn.execute(sa.select(sa.func.count()).select_from(modules).where(modules.c.semester_number.is_(None))).scalar_one():
        raise RuntimeError("Cannot downgrade: catalog modules may have no permanent semester")
    op.drop_index("ix_sections_cohort_semester_id", table_name="sections")
    with op.batch_alter_table("sections") as batch:
        batch.drop_constraint("fk_sections_cohort_semester_id", type_="foreignkey")
        batch.drop_column("cohort_semester_id")
    with op.batch_alter_table("modules") as batch:
        batch.alter_column("semester_number", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("module_offerings") as batch:
        batch.drop_column("inherit_all_sections")
