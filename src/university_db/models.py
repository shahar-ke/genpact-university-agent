"""SQLAlchemy declarative models mirroring ddl/schema.sql.

schema.sql is the authoritative DDL (applied at init time). These models mirror it
for ORM-based seeding and typed queries inside university_db. They are NOT used by
the agent — the agent only ever sees raw SQL through the MCP boundary.

The test suite applies schema.sql and then exercises these models, so any drift
between the two surfaces as a test failure.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base shared by all university_db ORM models."""


class Student(Base):
    """An enrolled student; owns a set of enrollments."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student")


class Teacher(Base):
    """An instructor; teaches one or more course offerings."""

    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)

    offerings: Mapped[list[CourseOffering]] = relationship(back_populates="teacher")


class Course(Base):
    """A catalog course, identified by a unique code; offered across semesters."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True, nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)

    offerings: Mapped[list[CourseOffering]] = relationship(back_populates="course")


class Semester(Base):
    """A term/year period; unique per (term, year)."""

    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("term", "year"),
        CheckConstraint("term IN ('Fall', 'Spring', 'Summer')", name="ck_semester_term"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)

    offerings: Mapped[list[CourseOffering]] = relationship(back_populates="semester")


class CourseOffering(Base):
    """A course taught by a teacher in a given semester; unique per (course, semester)."""

    __tablename__ = "course_offerings"
    __table_args__ = (UniqueConstraint("course_id", "semester_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"), nullable=False)

    course: Mapped[Course] = relationship(back_populates="offerings")
    teacher: Mapped[Teacher] = relationship(back_populates="offerings")
    semester: Mapped[Semester] = relationship(back_populates="offerings")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="offering")


class Enrollment(Base):
    """A student's participation in an offering; grade is NULL until graded."""

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "offering_id"),
        CheckConstraint("grade >= 0 AND grade <= 100", name="ck_enrollment_grade"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id"), nullable=False)
    grade: Mapped[float | None] = mapped_column(nullable=True)  # NULL = not yet graded

    student: Mapped[Student] = relationship(back_populates="enrollments")
    offering: Mapped[CourseOffering] = relationship(back_populates="enrollments")


class User(Base):
    """A login account: a student or teacher is bound to that identity; an admin to neither."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'teacher', 'admin')", name="ck_user_role"),
        CheckConstraint(
            "(role = 'student' AND student_id IS NOT NULL AND teacher_id IS NULL) OR "
            "(role = 'teacher' AND teacher_id IS NOT NULL AND student_id IS NULL) OR "
            "(role = 'admin'   AND student_id IS NULL AND teacher_id IS NULL)",
            name="ck_user_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, nullable=False)
    role: Mapped[str] = mapped_column(nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
