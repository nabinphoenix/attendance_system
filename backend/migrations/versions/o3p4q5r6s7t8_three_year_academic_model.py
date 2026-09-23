'''Add the three-year batch, level, and permanent-section academic model.'''

from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa


revision = 'o3p4q5r6s7t8'
down_revision = 'n2o3p4q5r6s7'
branch_labels = None
depends_on = None


def three_year_end(start: date) -> date:
    try:
        return start.replace(year=start.year + 3) - timedelta(days=1)
    except ValueError:
        return start.replace(year=start.year + 3, day=28) - timedelta(days=1)


def upgrade():
    with op.batch_alter_table('batches') as batch:
        batch.add_column(sa.Column('start_date', sa.Date(), nullable=True))
        batch.add_column(sa.Column('end_date', sa.Date(), nullable=True))

    conn = op.get_bind()
    batches = sa.table(
        'batches',
        sa.column('id', sa.Integer()),
        sa.column('college_id', sa.Integer()),
        sa.column('start_date', sa.Date()),
        sa.column('end_date', sa.Date()),
    )
    cohorts = sa.table(
        'cohort_semesters',
        sa.column('id', sa.Integer()),
        sa.column('batch_id', sa.Integer()),
        sa.column('intake_id', sa.Integer()),
        sa.column('semester_number', sa.Integer()),
        sa.column('start_date', sa.Date()),
        sa.column('batch_level_id', sa.Integer()),
    )
    intakes = sa.table(
        'intakes',
        sa.column('id', sa.Integer()),
        sa.column('start_date', sa.Date()),
    )
    for row in conn.execute(sa.select(batches.c.id)):
        cohort_start = conn.execute(
            sa.select(sa.func.min(cohorts.c.start_date)).where(cohorts.c.batch_id == row.id)
        ).scalar_one_or_none()
        intake_start = conn.execute(
            sa.select(sa.func.min(intakes.c.start_date))
            .select_from(intakes.join(cohorts, cohorts.c.intake_id == intakes.c.id))
            .where(cohorts.c.batch_id == row.id)
        ).scalar_one_or_none()
        start = intake_start or cohort_start or date.today()
        conn.execute(
            batches.update().where(batches.c.id == row.id).values(
                start_date=start,
                end_date=three_year_end(start),
            )
        )

    with op.batch_alter_table('batches') as batch:
        batch.alter_column('start_date', existing_type=sa.Date(), nullable=False)
        batch.alter_column('end_date', existing_type=sa.Date(), nullable=False)
        batch.create_check_constraint('ck_batch_dates', 'start_date <= end_date')

    with op.batch_alter_table('intakes') as batch:
        batch.alter_column('name', existing_type=sa.String(length=100), nullable=True)
        batch.alter_column('start_date', existing_type=sa.Date(), nullable=True)

    op.create_table(
        'batch_levels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level_number', sa.Integer(), nullable=False),
        sa.Column('intake_id', sa.Integer(), sa.ForeignKey('intakes.id'), nullable=False),
        sa.Column('college_id', sa.Integer(), sa.ForeignKey('colleges.id'), nullable=False),
        sa.UniqueConstraint('batch_id', 'level_number', name='uq_batch_level_number'),
        sa.UniqueConstraint('batch_id', 'intake_id', name='uq_batch_level_intake'),
        sa.CheckConstraint('level_number BETWEEN 1 AND 3', name='ck_batch_level_number'),
    )
    op.create_index('ix_batch_levels_batch_id', 'batch_levels', ['batch_id'])
    op.create_index('ix_batch_levels_college_id', 'batch_levels', ['college_id'])

    with op.batch_alter_table('cohort_semesters') as batch:
        batch.add_column(sa.Column('batch_level_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_cohort_semesters_batch_level_id',
            'batch_levels',
            ['batch_level_id'],
            ['id'],
        )
    op.create_index('ix_cohort_semesters_batch_level_id', 'cohort_semesters', ['batch_level_id'])

    levels = sa.table(
        'batch_levels',
        sa.column('id', sa.Integer()),
        sa.column('batch_id', sa.Integer()),
        sa.column('level_number', sa.Integer()),
        sa.column('intake_id', sa.Integer()),
        sa.column('college_id', sa.Integer()),
    )
    batch_college = dict(
        conn.execute(sa.select(batches.c.id, batches.c.college_id)).tuples().all()
    )
    level_ids = {}
    rows = conn.execute(
        sa.select(
            cohorts.c.id,
            cohorts.c.batch_id,
            cohorts.c.intake_id,
            cohorts.c.semester_number,
        ).order_by(cohorts.c.id)
    ).all()
    for row in rows:
        if row.semester_number not in range(1, 7):
            raise RuntimeError(
                f'Cohort semester {row.id} has invalid semester number {row.semester_number!r}'
            )
        level_number = ((row.semester_number - 1) // 2) + 1
        key = (row.batch_id, level_number)
        existing = level_ids.get(key)
        if existing is None:
            existing_row = conn.execute(
                sa.select(levels.c.id, levels.c.intake_id).where(
                    levels.c.batch_id == row.batch_id,
                    levels.c.level_number == level_number,
                )
            ).first()
            if existing_row and existing_row.intake_id != row.intake_id:
                raise RuntimeError(
                    f'Batch {row.batch_id} Level {level_number} has multiple intake codes'
                )
            existing = existing_row.id if existing_row else conn.execute(
                levels.insert().values(
                    batch_id=row.batch_id,
                    level_number=level_number,
                    intake_id=row.intake_id,
                    college_id=batch_college[row.batch_id],
                ).returning(levels.c.id)
            ).scalar_one()
            level_ids[key] = existing
        conn.execute(
            cohorts.update().where(cohorts.c.id == row.id).values(batch_level_id=existing)
        )

    with op.batch_alter_table('cohort_semesters') as batch:
        batch.alter_column('batch_level_id', existing_type=sa.Integer(), nullable=False)
        batch.alter_column('semester_number', existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint('uq_cohort_semester_context', type_='unique')
        batch.create_unique_constraint(
            'uq_cohort_semester_batch_sequence',
            ['batch_id', 'semester_number', 'attempt_number'],
        )
        batch.create_check_constraint(
            'ck_cohort_semester_number',
            'semester_number BETWEEN 1 AND 6',
        )

    with op.batch_alter_table('sections') as batch:
        batch.create_unique_constraint('uq_section_batch_name', ['batch_id', 'name'])


def downgrade():
    with op.batch_alter_table('sections') as batch:
        batch.drop_constraint('uq_section_batch_name', type_='unique')
    op.drop_index('ix_cohort_semesters_batch_level_id', table_name='cohort_semesters')
    with op.batch_alter_table('cohort_semesters') as batch:
        batch.drop_constraint('ck_cohort_semester_number', type_='check')
        batch.drop_constraint('uq_cohort_semester_batch_sequence', type_='unique')
        batch.create_unique_constraint(
            'uq_cohort_semester_context',
            ['intake_id', 'batch_id', 'semester_number', 'attempt_number'],
        )
        batch.drop_constraint('fk_cohort_semesters_batch_level_id', type_='foreignkey')
        batch.drop_column('batch_level_id')
    op.drop_index('ix_batch_levels_college_id', table_name='batch_levels')
    op.drop_index('ix_batch_levels_batch_id', table_name='batch_levels')
    op.drop_table('batch_levels')
    with op.batch_alter_table('intakes') as batch:
        batch.alter_column('start_date', existing_type=sa.Date(), nullable=False)
        batch.alter_column('name', existing_type=sa.String(length=100), nullable=False)
    with op.batch_alter_table('batches') as batch:
        batch.drop_constraint('ck_batch_dates', type_='check')
        batch.drop_column('end_date')
        batch.drop_column('start_date')
