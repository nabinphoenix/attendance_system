from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    db.info["college_id"] = -1  # deny data access until authenticated
    try:
        yield db
    finally:
        db.close()


# Register global tables and ownership enforcement for every entry point.
from app.modules.platform import models as platform_models  # noqa: E402,F401
from app.modules.google_workspace import models as google_workspace_models  # noqa: E402,F401
from app.core import tenancy  # noqa: E402,F401
