from urllib.parse import urlsplit
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.database import engine
from app.core.config import settings

def test_postgresql_database_is_migrated():
    assert engine.dialect.name == "postgresql"
    expected_revision = ScriptDirectory(str(Path(__file__).parents[1] / "migrations")).get_current_head()
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == expected_revision
        expected_database = urlsplit(settings.database_url).path.rsplit("/", 1)[-1]
        assert expected_database
        assert connection.scalar(text("select current_database()")) == expected_database
        index_definition = connection.scalar(text("select indexdef from pg_indexes where indexname = 'uq_active_case'"))
        assert index_definition and "UNIQUE INDEX" in index_definition and "status" in index_definition and "open" in index_definition
