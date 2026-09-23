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
    "teachers",
    "sections",
    "cohort_semesters",
    "batch_levels",
    "batches",
    "intakes",
    "notifications",
    "import_jobs",
    "agent_approvals",
    "audit_logs",
)

EXPECTED_PROGRAM_NAME = "BSc.IT"
EXPECTED_CATALOG_COUNT = 39
PRESERVED_CONFIGURATION_TABLES: tuple[str, ...] = (
    "colleges",
    "platform_configuration",
    "programs",
    "modules",
    "blocks",
    "rooms",
    "class_types",
    "time_slots",
    "campus_networks",
    "alembic_version",
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


def delete_resettable_data(conn: Connection) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for table in RESETTABLE_TABLES:
        result = conn.execute(text(f'DELETE FROM "{table}"'))
        deleted[table] = int(result.rowcount or 0)

    # All remaining users are academic/demo accounts.  The exact two IDs are
    # protected separately in reset_database(), after all user FKs are gone.
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
        verify_reset(conn, protected_accounts, program_before, catalog_before, revision_before)

    with engine.connect() as conn:
        verify_reset(conn, protected_accounts, program_before, catalog_before, revision_before)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run and args.confirm_live_reset:
        raise SystemExit("Use either --dry-run or --confirm-live-reset, not both")
    if not args.dry_run and not args.confirm_live_reset:
        raise SystemExit(
            "Refusing live deletion. Pass --confirm-live-reset explicitly."
        )
    reset_database(
        super_admin_id=args.super_admin_id,
        admin_id=args.admin_id,
        program_id=args.program_id,
        allow_legacy_super_admin_role=args.allow_legacy_super_admin_role,
        backup_dir=args.backup_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
