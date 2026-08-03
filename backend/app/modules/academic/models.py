from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)

class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))

class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    roll_number: Mapped[str] = mapped_column(String(50), unique=True)
    user = relationship("User")
    subjects: Mapped[list["Subject"]] = relationship(secondary="student_subject_enrollments", back_populates="students")

class Guardian(Base):
    __tablename__ = "guardians"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True)
    user = relationship("User")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    students: Mapped[list[Student]] = relationship(secondary="student_subject_enrollments", back_populates="subjects")

class StudentSubjectEnrollment(Base):
    __tablename__ = "student_subject_enrollments"
    __table_args__ = (UniqueConstraint("student_id", "subject_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
