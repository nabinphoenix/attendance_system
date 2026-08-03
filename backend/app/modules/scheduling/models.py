from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
class ScheduleOverride(Base):
    __tablename__ = "schedule_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
class ClassSession(Base):
    __tablename__ = "class_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
