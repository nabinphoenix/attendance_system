from sqlalchemy import text
from app.core.database import engine

def test_postgresql_database_is_migrated():
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == "0f378fa52e9c"
        assert connection.scalar(text("select current_database()")) == "antimbench"
