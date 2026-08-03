from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
class CoursePlan(Base):
    __tablename__ = "course_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
