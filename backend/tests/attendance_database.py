"""Disposable database engines for attendance integration tests.

Set ATTENDANCE_TEST_POSTGRES_URL to a loopback attendance_test database to run
the same route fixtures against PostgreSQL-native CIDR and INET fields.
"""

import os
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.database import Base


def make_attendance_engine():
    url = os.environ.get("ATTENDANCE_TEST_POSTGRES_URL")
    if not url:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        return engine, None

    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path != "/attendance_test":
        raise RuntimeError("Attendance PostgreSQL tests require a loopback attendance_test database")
    schema = f"attendance_test_{uuid4().hex[:12]}"
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin_engine.dispose()
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    # A migrated public schema also exists in this disposable database.
    # Force table creation in the isolated schema instead of accepting public
    # tables that PostgreSQL exposes through search_path.
    Base.metadata.create_all(engine, checkfirst=False)
    # The existing metadata hook seeds the default Techspire test college.
    return engine, schema


def dispose_attendance_engine(engine, schema):
    url = engine.url.render_as_string(hide_password=False)
    engine.dispose()
    if schema is not None:
        if not schema.startswith("attendance_test_"):
            raise RuntimeError("Refusing to drop an unexpected test schema")
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()
