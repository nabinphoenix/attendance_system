"""Multi-college ownership and platform administration.

All pre-existing records belong to Techspire College. This migration changes
ownership and identifier constraints without replacing any existing records.
"""
from alembic import op
import sqlalchemy as sa

revision = "i3d4e5f6g7h8"
down_revision = "h2c3d4e5f6g7"
branch_labels = None
depends_on = None

OWNED_TABLES = ['agent_approvals', 'attendance_challenges', 'attendance_changes', 'attendance_records', 'audit_logs', 'batches', 'blocks', 'case_interactions', 'check_in_attempts', 'class_sessions', 'class_types', 'cohort_semesters', 'course_plans', 'guardians', 'import_jobs', 'intakes', 'leave_requests', 'makeup_suggestions', 'module_offering_sections', 'module_offerings', 'modules', 'notifications', 'pending_attendance_verifications', 'programs', 'promotion_run_items', 'promotion_runs', 'rooms', 'routine_entries', 'routine_entry_sections', 'routine_pending_sections', 'schedule_overrides', 'sections', 'student_cases', 'student_enrollments', 'student_invitations', 'student_subject_enrollments', 'students', 'subjects', 'teachers', 'time_slots', 'timetable_entries', 'users']
LOCAL_KEYS = {"programs": ["name"], "intakes": ["name", "code"], "blocks": ["name"], "modules": ["code"], "class_types": ["name"], "students": ["roll_number"], "teachers": ["employee_code"], "subjects": ["code"]}


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'")
    op.create_table("colleges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("contact_email", sa.String(255)),
        sa.Column("address", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("INSERT INTO colleges (id, name, slug) VALUES (1, 'Techspire College', 'techspire')")
    if bind.dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('colleges', 'id'), 1)")
    op.create_table("platform_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_name", sa.String(150), nullable=False),
        sa.Column("support_email", sa.String(255)),
        sa.Column("allow_college_creation", sa.Boolean(), nullable=False))
    op.execute("INSERT INTO platform_configuration (id, platform_name, allow_college_creation) VALUES (1, 'AntimBench', true)")
    for name in OWNED_TABLES:
        op.add_column(name, sa.Column("college_id", sa.Integer(), nullable=name in {"users", "audit_logs"}, server_default="1"))
        op.create_foreign_key(f"fk_{name}_college", name, "colleges", ["college_id"], ["id"])
        op.create_index(f"ix_{name}_college_id", name, ["college_id"])
        op.alter_column(name, "college_id", server_default=None)
    inspector = sa.inspect(bind)
    for name, columns in LOCAL_KEYS.items():
        for constraint in inspector.get_unique_constraints(name):
            if constraint["column_names"] in [[col] for col in columns]:
                op.drop_constraint(constraint["name"], name, type_="unique")
        for col in columns:
            op.create_unique_constraint(f"uq_{name}_college_{col}", name, ["college_id", col])
    op.drop_constraint("uq_time_slot_range", "time_slots", type_="unique")
    op.create_unique_constraint("uq_time_slot_range", "time_slots", ["college_id", "start_time", "end_time"])
    op.create_check_constraint("ck_user_college_role", "users", "(role = 'SUPER_ADMIN' AND college_id IS NULL) OR (role <> 'SUPER_ADMIN' AND college_id IS NOT NULL)")
    # Database triggers also cover secondary-table and direct SQL writes. ORM
    # request scoping handles reads, including relationship loads and aggregates.
    if bind.dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION enforce_college_reference() RETURNS trigger AS $$
        DECLARE owner_id integer; reference_id integer;
        BEGIN
          IF TG_OP = 'UPDATE' AND OLD.college_id IS DISTINCT FROM NEW.college_id THEN
            RAISE EXCEPTION 'Existing records cannot be moved between colleges' USING ERRCODE = '23514';
          END IF;
          IF TG_NARGS > 0 THEN
            reference_id := (to_jsonb(NEW)->>TG_ARGV[1])::integer;
            IF reference_id IS NOT NULL THEN
              EXECUTE format('SELECT college_id FROM %I.%I WHERE id = $1', TG_TABLE_SCHEMA, TG_ARGV[0]) INTO owner_id USING reference_id;
              IF NEW.college_id IS NULL AND owner_id IS NOT NULL THEN
                NEW.college_id := owner_id;
              END IF;
              IF owner_id IS DISTINCT FROM NEW.college_id AND NOT (TG_ARGV[2] = 'actor' AND owner_id IS NULL) THEN
                RAISE EXCEPTION 'Related records must belong to the same college' USING ERRCODE = '23514';
              END IF;
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        inspector = sa.inspect(bind)
        actors = {"actor_id", "uploaded_by", "created_by", "approved_by", "changed_by", "staff_id", "requested_by"}
        for name in OWNED_TABLES:
            op.execute(f'CREATE TRIGGER college_owner_immutable BEFORE UPDATE ON "{name}" FOR EACH ROW EXECUTE FUNCTION enforce_college_reference()')
            for fk in inspector.get_foreign_keys(name):
                target = fk["referred_table"]
                cols = fk["constrained_columns"]
                if target not in OWNED_TABLES or len(cols) != 1: continue
                col = cols[0]
                mode = "actor" if target == "users" and col in actors else "relation"
                op.execute(f"CREATE TRIGGER college_ref_{col} BEFORE INSERT OR UPDATE ON \"{name}\" FOR EACH ROW EXECUTE FUNCTION enforce_college_reference('{target}', '{col}', '{mode}')")


def downgrade():
    raise RuntimeError("This migration cannot safely merge multiple colleges. Restore a pre-migration backup instead.")
