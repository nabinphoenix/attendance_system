from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class StudentCase(Base):
    __tablename__ = "student_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
class CaseInteraction(Base):
    __tablename__ = "case_interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
