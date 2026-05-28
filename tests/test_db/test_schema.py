"""Apply the authoritative DDL, then exercise the ORM against it.

This doubles as a drift guard: if schema.sql and models.py diverge (column names,
types, constraints), these tests fail.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from university_db.engine import make_engine, session_scope
from university_db.models import (
    Course,
    CourseOffering,
    Enrollment,
    Semester,
    Student,
    Teacher,
)
from university_db.schema import apply_schema


def _seed_minimal(engine):
    with session_scope(engine) as s:
        student = Student(name="Alice", email="alice@uni.edu")
        teacher = Teacher(name="Dr. Bob", email="bob@uni.edu")
        course = Course(code="CS101", title="Intro to CS")
        semester = Semester(term="Fall", year=2025)
        s.add_all([student, teacher, course, semester])
        s.flush()
        offering = CourseOffering(
            course_id=course.id, teacher_id=teacher.id, semester_id=semester.id
        )
        s.add(offering)
        s.flush()
        s.add(Enrollment(student_id=student.id, offering_id=offering.id, grade=92.5))


def test_schema_applies_and_models_roundtrip(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}", read_only=False)
    apply_schema(engine)
    _seed_minimal(engine)

    with session_scope(engine) as s:
        rows = s.execute(
            select(Student.name, Enrollment.grade).join(
                Enrollment, Enrollment.student_id == Student.id
            )
        ).all()
    assert rows == [("Alice", 92.5)]


def test_foreign_keys_are_enforced(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'fk.db'}", read_only=False)
    apply_schema(engine)

    # FK pragma must reject an enrollment referencing a non-existent student.
    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(Enrollment(student_id=999, offering_id=999, grade=50.0))


def test_grade_check_constraint(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'grade.db'}", read_only=False)
    apply_schema(engine)
    _seed_minimal(engine)

    # grade > 100 violates the CHECK constraint.
    with pytest.raises(IntegrityError), session_scope(engine) as s:
        offering_id = s.execute(select(CourseOffering.id)).scalar_one()
        student = Student(name="Eve", email="eve@uni.edu")
        s.add(student)
        s.flush()
        s.add(Enrollment(student_id=student.id, offering_id=offering_id, grade=150.0))
