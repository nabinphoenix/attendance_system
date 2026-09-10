'''dated cohort semesters and auditable student promotions

Revision ID: g1b2c3d4e5f6
Revises: f8a9b0c1d2e3
'''

from alembic import op
import sqlalchemy as sa


revision = 'g1b2c3d4e5f6'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cohort_semesters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('intake_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('semester_number', sa.Integer(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='planned', nullable=False),
        sa.ForeignKeyConstraint(['intake_id'], ['intakes.id']),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'intake_id',
            'batch_id',
            'semester_number',
            'attempt_number',
            name='uq_cohort_semester_context',
        ),
        sa.CheckConstraint('start_date <= end_date', name='ck_cohort_semester_dates'),
    )
    op.create_index(
        'ix_cohort_semesters_context',
        'cohort_semesters',
        ['intake_id', 'batch_id', 'semester_number'],
    )

    with op.batch_alter_table('module_offerings') as batch:
        batch.add_column(sa.Column('cohort_semester_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_module_offerings_cohort_semester',
            'cohort_semesters',
            ['cohort_semester_id'],
            ['id'],
        )
    op.create_index(
        'ix_module_offerings_cohort_semester_id',
        'module_offerings',
        ['cohort_semester_id'],
    )

    with op.batch_alter_table('routine_entries') as batch:
        batch.add_column(sa.Column('cohort_semester_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_routine_entries_cohort_semester',
            'cohort_semesters',
            ['cohort_semester_id'],
            ['id'],
        )
    op.create_index(
        'ix_routine_entries_cohort_semester_id',
        'routine_entries',
        ['cohort_semester_id'],
    )

    op.create_table(
        'promotion_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('intake_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('from_cohort_semester_id', sa.Integer(), nullable=False),
        sa.Column('to_cohort_semester_id', sa.Integer(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='applied', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['intake_id'], ['intakes.id']),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.ForeignKeyConstraint(['from_cohort_semester_id'], ['cohort_semesters.id']),
        sa.ForeignKeyConstraint(['to_cohort_semester_id'], ['cohort_semesters.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'intake_id',
            'batch_id',
            'from_cohort_semester_id',
            'to_cohort_semester_id',
            'effective_date',
            name='uq_promotion_run_transition',
        ),
    )
    op.create_index(
        'ix_promotion_runs_context',
        'promotion_runs',
        ['intake_id', 'batch_id', 'effective_date'],
    )

    op.create_table(
        'student_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('cohort_semester_id', sa.Integer(), nullable=True),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('promotion_run_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id']),
        sa.ForeignKeyConstraint(['cohort_semester_id'], ['cohort_semesters.id']),
        sa.ForeignKeyConstraint(['promotion_run_id'], ['promotion_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            'ends_on IS NULL OR starts_on < ends_on',
            name='ck_student_enrollment_dates',
        ),
    )
    op.create_index(
        'ix_student_enrollments_student_dates',
        'student_enrollments',
        ['student_id', 'starts_on', 'ends_on'],
    )
    op.create_index(
        'ix_student_enrollments_section_dates',
        'student_enrollments',
        ['section_id', 'starts_on', 'ends_on'],
    )
    op.create_index(
        'ix_student_enrollments_cohort_semester_id',
        'student_enrollments',
        ['cohort_semester_id'],
    )
    op.create_index(
        'ix_student_enrollments_promotion_run_id',
        'student_enrollments',
        ['promotion_run_id'],
    )

    op.create_table(
        'promotion_run_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('promotion_run_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('source_enrollment_id', sa.Integer(), nullable=True),
        sa.Column('target_enrollment_id', sa.Integer(), nullable=True),
        sa.Column('source_section_id', sa.Integer(), nullable=False),
        sa.Column('target_section_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['promotion_run_id'], ['promotion_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_enrollment_id'], ['student_enrollments.id']),
        sa.ForeignKeyConstraint(['target_enrollment_id'], ['student_enrollments.id']),
        sa.ForeignKeyConstraint(['source_section_id'], ['sections.id']),
        sa.ForeignKeyConstraint(['target_section_id'], ['sections.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('promotion_run_id', 'student_id', name='uq_promotion_run_item_student'),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            '''
            INSERT INTO student_enrollments
                (student_id, section_id, starts_on, status)
            SELECT s.id, s.section_id,
                   COALESCE(i.start_date, '1970-01-01'),
                   'active'
            FROM students s
            LEFT JOIN sections sec ON sec.id = s.section_id
            LEFT JOIN intakes i ON i.id = sec.intake_id
            WHERE NOT EXISTS (
                SELECT 1 FROM student_enrollments se WHERE se.student_id = s.id
            )
            '''
        )
    )


def downgrade() -> None:
    op.drop_table('promotion_run_items')
    op.drop_index('ix_student_enrollments_promotion_run_id', table_name='student_enrollments')
    op.drop_index('ix_student_enrollments_cohort_semester_id', table_name='student_enrollments')
    op.drop_index('ix_student_enrollments_section_dates', table_name='student_enrollments')
    op.drop_index('ix_student_enrollments_student_dates', table_name='student_enrollments')
    op.drop_table('student_enrollments')
    op.drop_index('ix_promotion_runs_context', table_name='promotion_runs')
    op.drop_table('promotion_runs')
    op.drop_index('ix_routine_entries_cohort_semester_id', table_name='routine_entries')
    with op.batch_alter_table('routine_entries') as batch:
        batch.drop_constraint('fk_routine_entries_cohort_semester', type_='foreignkey')
        batch.drop_column('cohort_semester_id')
    op.drop_index('ix_module_offerings_cohort_semester_id', table_name='module_offerings')
    with op.batch_alter_table('module_offerings') as batch:
        batch.drop_constraint('fk_module_offerings_cohort_semester', type_='foreignkey')
        batch.drop_column('cohort_semester_id')
    op.drop_index('ix_cohort_semesters_context', table_name='cohort_semesters')
    op.drop_table('cohort_semesters')
