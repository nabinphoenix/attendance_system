"""Safely reset live academic/demo data while preserving platform accounts and catalog.

Run from ``backend``.  The live reset path is intentionally explicit:

    python reset_academic_data.py --confirm-live-reset \
        --super-admin-id 2 --admin-id 2 --program-id 18 \
        --allow-legacy-super-admin-role

The account IDs must be supplied from a prior inspection of the live database.
The legacy flag is required only when the platform Super Admin is stored with
the historical ``ADMIN`` enum value, as documented by this application.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import engine


RESETTABLE_TABLES: tuple[str, ...] = (
    "pending_attendance_verifications",
    "attendance_changes",
    "attendance_records",
    "check_in_attempts",
    "attendance_challenges",
    "leave_requests",
    "case_interactions",
    "student_cases",
    "attendance_threshold_alerts",
    "student_invitations",
    "makeup_suggestions",
    "academic_calendars",
    "teacher_feedback",
    "class_sessions",
    "schedule_overrides",
    "routine_entry_sections",
    "routine_pending_sections",
    "routine_entries",
    "course_plans",
    "module_offering_sections",
    "module_offerings",
    "promotion_run_items",
    "student_enrollments",
    "promotion_runs",
    "student_subject_enrollments",
    "timetable_entries",
    "subjects",
    "guardians",
    "students",
    "sections",
    "cohort_semesters",
    "batch_levels",
    "batches",
    "intakes",
)
EXPECTED_PROGRAM_NAME = "BSc.IT"
EXPECTED_CATALOG_COUNT = 39
PRESERVED_CONFIGURATION_TABLES: tuple[str, ...] = (
    "colleges",
    "platform_configuration",
    "programs",
    "modules",
    "teachers",
    "blocks",
    "rooms",
    "class_types",
    "time_slots",
    "campus_networks",
    "notifications",
    "import_jobs",
    "agent_approvals",
    "alembic_version",
)
# Reset only notification/audit data that belongs to student records being
# removed.  Staff/system notifications, import history, approvals, and their
# configuration remain intact as requested for the live presentation reset.
STUDENT_NOTIFICATION_RECIPIENT_TYPES: tuple[str, ...] = ("student", "guardian")
STUDENT_NOTIFICATION_RELATED_ENTITY_TYPES: tuple[str, ...] = (
    "student_invitation",
    "attendance_threshold_alert",
    "student_case",
    "promotion_run",
)
STUDENT_ACADEMIC_AUDIT_ENTITY_TYPES: tuple[str, ...] = (
    "student",
    "students",
    "student_enrollment",
    "student_enrollments",
    "student_invitation",
    "student_invitations",
    "guardian",
    "guardians",
    "batch",
    "batches",
    "batch_level",
    "batch_levels",
    "intake",
    "intakes",
    "section",
    "sections",
    "cohort_semester",
    "module_offering",
    "routine_entry",
    "class_session",
    "attendance_record",
    "attendance_threshold_alert",
    "promotion_run",
)
USER_COLUMNS = (
    "id",
    "name",
    "email",
    "password_hash",
    "avatar_key",
    "avatar_data",
    "avatar_content_type",
    "role::text AS role",
    "college_id",
    "is_active",
    "created_at",
)


class ResetError(RuntimeError):
    """Raised when a safety check fails."""


def table_count(conn: Connection, table: str) -> int:
    return int(conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())


def table_counts(conn: Connection, tables: Iterable[str]) -> dict[str, int]:
    return {table: table_count(conn, table) for table in tables}


def protected_user(conn: Connection, user_id: int) -> dict[str, Any]:
    query = text(
        f'SELECT {", ".join(USER_COLUMNS)} FROM users WHERE id = :user_id'
    )
    row = conn.execute(query, {"user_id": user_id}).mappings().one_or_none()
    if row is None:
        raise ResetError(f"Protected user ID {user_id} does not exist")
    return dict(row)


def snapshot_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(before.get(column) == after.get(column) for column in before)


def validate_protected_accounts(
    conn: Connection,
    super_admin_id: int,
    admin_id: int,
    allow_legacy_super_admin_role: bool,
) -> dict[int, dict[str, Any]]:
    accounts: dict[int, dict[str, Any]] = {}
    for user_id in {super_admin_id, admin_id}:
        accounts[user_id] = protected_user(conn, user_id)

    admin = accounts[admin_id]
    if admin["role"] != "ADMIN":
        raise ResetError(
            f"Admin preservation ID {admin_id} has role {admin['role']!r}, expected ADMIN"
        )

    super_admin = accounts[super_admin_id]
    if super_admin["role"] != "SUPER_ADMIN":
        if not (
            allow_legacy_super_admin_role
            and super_admin["role"] == "ADMIN"
        ):
            raise ResetError(
                f"Super Admin preservation ID {super_admin_id} has role "
                f"{super_admin['role']!r}; pass --allow-legacy-super-admin-role "
                "only after confirming this is the documented legacy account"
            )
    return accounts


def protected_teacher_accounts(conn: Connection) -> dict[int, dict[str, Any]]:
    """Return immutable snapshots of every existing teacher login.

    The live reset replaces academic operations, not the staff directory.  A
    teacher without a matching TEACHER user is unsafe to preserve because the
    service would be left with a broken identity relationship.
    """
    teacher_user_ids = conn.execute(
        text("SELECT user_id FROM teachers ORDER BY user_id")
    ).scalars().all()
    accounts: dict[int, dict[str, Any]] = {}
    for user_id in teacher_user_ids:
        account = protected_user(conn, int(user_id))
        if account["role"] != "TEACHER":
            raise ResetError(
                f"Teacher user ID {user_id} has role {account['role']!r}, expected TEACHER"
            )
        accounts[int(user_id)] = account
    if not accounts:
        raise ResetError("No teachers exist; refusing to replace presentation academic data")
    return accounts


def teacher_snapshot(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, user_id, employee_code, college_id "
            "FROM teachers ORDER BY id"
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def notification_preservation_condition() -> str:
    recipient_types = ", ".join(
        f"'{recipient_type}'" for recipient_type in STUDENT_NOTIFICATION_RECIPIENT_TYPES
    )
    related_entities = ", ".join(
        f"'{entity_type}'" for entity_type in STUDENT_NOTIFICATION_RELATED_ENTITY_TYPES
    )
    return (
        f"recipient_type NOT IN ({recipient_types}) AND "
        f"(related_entity IS NULL OR related_entity NOT IN ({related_entities}))"
    )


def preserved_notifications_snapshot(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, recipient_type, recipient_id, channel, subject, body, html_body, "
            "status::text AS status, related_entity, related_entity_id, actor_id, "
            "delivery_attempts, last_attempt_at, next_attempt_at, failure_reason, "
            "created_at, sent_at, college_id FROM notifications WHERE "
            + notification_preservation_condition()
            + " ORDER BY id"
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def catalog_snapshot(conn: Connection) -> dict[str, Any]:
    rows = conn.execute(
        text(
            "SELECT id, college_id, code, title, credits, semester_number "
            "FROM modules ORDER BY id"
        )
    ).mappings().all()
    duplicate_codes = conn.execute(
        text(
            "SELECT code, count(*) AS count FROM modules "
            "GROUP BY code HAVING count(*) > 1 ORDER BY code"
        )
    ).mappings().all()
    return {
        "count": len(rows),
        "records": [dict(row) for row in rows],
        "duplicate_codes": [dict(row) for row in duplicate_codes],
    }


def protected_program(conn: Connection, program_id: int) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT id, name, college_id FROM programs WHERE id = :program_id"),
        {"program_id": program_id},
    ).mappings().one_or_none()
    if row is None:
        raise ResetError(f"Protected Program ID {program_id} does not exist")
    return dict(row)


def migration_revision(conn: Connection) -> str:
    return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def create_backup(backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"antimbench-live-before-academic-reset-{timestamp}.dump"
    url = make_url(settings.database_url)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    command = [
        "pg_dump",
        "--format=custom",
        "--file",
        str(backup_path),
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 5432),
        "--username",
        url.username or "",
        "--dbname",
        url.database or "",
    ]
    try:
        subprocess.run(command, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResetError("PostgreSQL backup failed; no data was changed") from exc
    return backup_path


def delete_student_audits(conn: Connection) -> int:
    audit_entities = ", ".join(
        f"'{entity_type}'" for entity_type in STUDENT_ACADEMIC_AUDIT_ENTITY_TYPES
    )
    result = conn.execute(
        text(
            "DELETE FROM audit_logs WHERE actor_id IN ("
            "SELECT id FROM users WHERE role::text = 'STUDENT'"
            f") OR entity_type IN ({audit_entities})"
        )
    )
    return int(result.rowcount or 0)


def delete_student_notifications(conn: Connection) -> int:
    recipient_types = ", ".join(
        f"'{recipient_type}'" for recipient_type in STUDENT_NOTIFICATION_RECIPIENT_TYPES
    )
    related_entities = ", ".join(
        f"'{entity_type}'" for entity_type in STUDENT_NOTIFICATION_RELATED_ENTITY_TYPES
    )
    result = conn.execute(
        text(
            "DELETE FROM notifications WHERE "
            f"recipient_type IN ({recipient_types}) OR related_entity IN ({related_entities})"
        )
    )
    return int(result.rowcount or 0)


def delete_resettable_data(conn: Connection) -> dict[str, int]:
    deleted: dict[str, int] = {
        "student_academic_audit_logs": delete_student_audits(conn),
    }
    for table in RESETTABLE_TABLES:
        result = conn.execute(text(f'DELETE FROM "{table}"'))
        deleted[table] = int(result.rowcount or 0)
    # Attendance alerts reference their queued notification.  Delete alerts
    # first, then remove only the notifications associated with old students.
    deleted["student_notifications"] = delete_student_notifications(conn)
    return deleted

def delete_non_protected_users(
    conn: Connection, protected_ids: tuple[int, ...]
) -> int:
    placeholders = ", ".join(f":protected_{index}" for index in range(len(protected_ids)))
    params = {f"protected_{index}": user_id for index, user_id in enumerate(protected_ids)}
    result = conn.execute(
        text(f"DELETE FROM users WHERE id NOT IN ({placeholders})"), params
    )
    return int(result.rowcount or 0)


def verify_reset(
    conn: Connection,
    protected_accounts: dict[int, dict[str, Any]],
    program_before: dict[str, Any],
    catalog_before: dict[str, Any],
    teacher_before: list[dict[str, Any]],
    preserved_notifications_before: list[dict[str, Any]],
    revision_before: str,
) -> None:
    for user_id, before in protected_accounts.items():
        after = protected_user(conn, user_id)
        if not snapshot_equal(before, after):
            raise ResetError(f"Protected user ID {user_id} changed during reset")

    protected_ids = set(protected_accounts)
    remaining_users = table_count(conn, "users")
    if remaining_users != len(protected_ids):
        raise ResetError(
            f"Expected {len(protected_ids)} preserved users, found {remaining_users}"
        )

    if teacher_snapshot(conn) != teacher_before:
        raise ResetError("Teacher directory changed during reset")
    if preserved_notifications_snapshot(conn) != preserved_notifications_before:
        raise ResetError("System/staff notifications changed during reset")

    if migration_revision(conn) != revision_before:
        raise ResetError("Migration revision changed during reset")

    program_after = protected_program(conn, int(program_before["id"]))
    if program_after != program_before:
        raise ResetError(f"Protected Program ID {program_before['id']} changed during reset")

    catalog_after = catalog_snapshot(conn)
    if catalog_after != catalog_before:
        raise ResetError("Course/module catalog changed during reset")
    if catalog_after["duplicate_codes"]:
        raise ResetError("Duplicate course/module codes exist in the catalog")

    remaining = table_counts(conn, RESETTABLE_TABLES)
    non_empty = {table: count for table, count in remaining.items() if count}
    if non_empty:
        raise ResetError(f"Resettable records remain: {non_empty}")


def reset_database(
    *,
    super_admin_id: int,
    admin_id: int,
    program_id: int,
    allow_legacy_super_admin_role: bool,
    backup_dir: Path,
    verified_rds_snapshot: str | None,
    dry_run: bool,
) -> None:
    with engine.connect() as conn:
        revision_before = migration_revision(conn)
        protected_accounts = validate_protected_accounts(
            conn,
            super_admin_id,
            admin_id,
            allow_legacy_super_admin_role,
        )
        teacher_accounts = protected_teacher_accounts(conn)
        overlap = set(protected_accounts).intersection(teacher_accounts)
        if overlap:
            raise ResetError(f"Administrator and teacher preservation IDs overlap: {sorted(overlap)}")
        protected_accounts.update(teacher_accounts)
        teacher_before = teacher_snapshot(conn)
        preserved_notifications_before = preserved_notifications_snapshot(conn)
        program_before = protected_program(conn, program_id)
        catalog_before = catalog_snapshot(conn)
        if program_before["name"].strip().casefold() != EXPECTED_PROGRAM_NAME.casefold():
            raise ResetError(
                f"Protected Program ID {program_id} is {program_before['name']!r}, "
                f"expected {EXPECTED_PROGRAM_NAME!r}"
            )
        if catalog_before["count"] != EXPECTED_CATALOG_COUNT:
            raise ResetError(
                f"Expected {EXPECTED_CATALOG_COUNT} course/module records, "
                f"found {catalog_before['count']}"
            )
        if catalog_before["duplicate_codes"]:
            raise ResetError(
                f"Duplicate course/module codes exist: {catalog_before['duplicate_codes']}"
            )
        before_counts = table_counts(conn, RESETTABLE_TABLES)
        preserved_counts = table_counts(conn, PRESERVED_CONFIGURATION_TABLES)
        protected_ids = tuple(sorted(protected_accounts))
        placeholders = ", ".join(f":protected_{index}" for index in range(len(protected_ids)))
        params = {f"protected_{index}": user_id for index, user_id in enumerate(protected_ids)}
        non_protected_users = int(conn.execute(
            text(f"SELECT count(*) FROM users WHERE id NOT IN ({placeholders})"),
            params,
        ).scalar_one())

        print(f"Migration revision: {revision_before}")
        for user_id, account in protected_accounts.items():
            password_fingerprint = hashlib.sha256(
                account["password_hash"].encode("utf-8")
            ).hexdigest()
            print(
                f"Preserving user ID {user_id}: {account['email']} "
                f"(stored role {account['role']}, password hash length "
                f"{len(account['password_hash'])}, SHA-256 {password_fingerprint})"
            )
        print(
            f"Preserving Program ID {program_before['id']}: {program_before['name']} "
            f"(college {program_before['college_id']})"
        )
        print(f"Course/module catalog records: {catalog_before['count']}")
        print("Preserved reusable/configuration rows:")
        for table, count in preserved_counts.items():
            print(f"  {table}: {count}")
        print("Proposed deletions by table:")
        for table, count in before_counts.items():
            print(f"  {table}: {count}")
        print(f"  users (excluding protected IDs): {non_protected_users}")
        print(f"Total proposed row deletions: {sum(before_counts.values()) + non_protected_users}")

        if dry_run:
            print("Dry run only: no backup or deletion performed.")
            return

    if verified_rds_snapshot:
        print(f"Using verified RDS snapshot backup: {verified_rds_snapshot}")
    else:
        backup_path = create_backup(backup_dir)
        print(f"Backup created: {backup_path}")

    protected_ids = tuple(sorted(protected_accounts))
    # Use a fresh transaction after the preflight connection is closed.  This
    # avoids accidentally committing any preflight read transaction together
    # with the destructive work.
    with engine.begin() as conn:
        # Serialize concurrent invocations of this command.  The application
        # does not use this advisory lock, so execute during a maintenance
        # window to prevent new writes.
        conn.execute(text("SELECT pg_advisory_xact_lock(7284192601)"))

        # Re-read the whitelist after the backup.  If an account was changed
        # between preflight and the transaction, abort.
        for user_id, before in protected_accounts.items():
            current = protected_user(conn, user_id)
            if not snapshot_equal(before, current):
                raise ResetError(
                    f"Protected user ID {user_id} changed before deletion"
                )

        delete_resettable_data(conn)
        delete_non_protected_users(conn, protected_ids)
        verify_reset(
            conn,
            protected_accounts,
            program_before,
            catalog_before,
            teacher_before,
            preserved_notifications_before,
            revision_before,
        )

    with engine.connect() as conn:
        verify_reset(
            conn,
            protected_accounts,
            program_before,
            catalog_before,
            teacher_before,
            preserved_notifications_before,
            revision_before,
        )
    print("Controlled academic reset completed and verified.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--super-admin-id", type=int, required=True)
    parser.add_argument("--admin-id", type=int, required=True)
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--allow-legacy-super-admin-role", action="store_true")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Directory for the custom-format PostgreSQL backup",
    )
    parser.add_argument(
        "--verified-rds-snapshot",
        help="Exact identifier of an already verified available RDS snapshot",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run and args.confirm_live_reset:
        raise SystemExit("Use either --dry-run or --confirm-live-reset, not both")
    if not args.dry_run and not args.confirm_live_reset:
        raise SystemExit(
            "Refusing live deletion. Pass --confirm-live-reset explicitly."
        )
    if args.confirm_live_reset and not args.verified_rds_snapshot:
        raise SystemExit(
            "Live reset requires --verified-rds-snapshot or the pg_dump backup path. "
            "Supply the verified snapshot identifier explicitly."
        )
    reset_database(
        super_admin_id=args.super_admin_id,
        admin_id=args.admin_id,
        program_id=args.program_id,
        allow_legacy_super_admin_role=args.allow_legacy_super_admin_role,
        backup_dir=args.backup_dir,
        verified_rds_snapshot=args.verified_rds_snapshot,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
