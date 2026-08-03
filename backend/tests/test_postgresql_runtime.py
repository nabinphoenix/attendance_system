from sqlalchemy import text
from app.core.database import engine

def test_postgresql_database_is_migrated():
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == "9647971e5956"
        assert connection.scalar(text("select current_database()")) == "antimbench"
        index_definition = connection.scalar(text("select indexdef from pg_indexes where indexname = 'uq_active_case'"))
        assert index_definition and "UNIQUE INDEX" in index_definition and "status" in index_definition and "open" in index_definition
