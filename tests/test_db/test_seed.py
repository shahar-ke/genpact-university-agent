"""Seed generator: counts, determinism, and data invariants."""

from sqlalchemy import func, select

from university_db.engine import make_engine, session_scope
from university_db.models import CourseOffering, Enrollment, Semester, User
from university_db.schema import apply_schema
from university_db.seed import SeedConfig, generate

SMALL = SeedConfig(teachers=4, students=12, courses=8, semesters=4, retakes=3)


def _fresh_engine(tmp_path, name):
    engine = make_engine(f"sqlite:///{tmp_path / name}", read_only=False)
    apply_schema(engine)
    return engine


def test_counts_match_config(tmp_path):
    engine = _fresh_engine(tmp_path, "counts.db")
    with session_scope(engine) as s:
        counts = generate(s, SMALL)
    assert counts["teachers"] == 4
    assert counts["students"] == 12
    assert counts["courses"] == 8
    assert counts["semesters"] == 4
    assert counts["users"] == 16  # one per student + one per teacher
    assert counts["enrollments"] > 0


def test_is_deterministic(tmp_path):
    rows_per_run = []
    for name in ("run_a.db", "run_b.db"):
        engine = _fresh_engine(tmp_path, name)
        with session_scope(engine) as s:
            generate(s, SMALL)
        with session_scope(engine) as s:
            query = select(
                Enrollment.student_id, Enrollment.offering_id, Enrollment.grade
            ).order_by(Enrollment.id)
            rows_per_run.append(s.execute(query).all())
    assert rows_per_run[0] == rows_per_run[1]


def test_grades_are_null_or_in_range(tmp_path):
    engine = _fresh_engine(tmp_path, "grades.db")
    with session_scope(engine) as s:
        generate(s, SMALL)
    with session_scope(engine) as s:
        grades = s.execute(select(Enrollment.grade)).scalars().all()
    assert any(g is not None for g in grades)
    assert all(g is None or 0.0 <= g <= 100.0 for g in grades)


def test_current_semester_is_ungraded(tmp_path):
    engine = _fresh_engine(tmp_path, "current.db")
    with session_scope(engine) as s:
        generate(s, SMALL)
    with session_scope(engine) as s:
        newest_semester_id = s.execute(
            select(Semester.id).order_by(Semester.year.desc(), Semester.id.desc()).limit(1)
        ).scalar_one()
        graded_in_current = s.execute(
            select(func.count())
            .select_from(Enrollment)
            .join(CourseOffering, Enrollment.offering_id == CourseOffering.id)
            .where(
                CourseOffering.semester_id == newest_semester_id,
                Enrollment.grade.is_not(None),
            )
        ).scalar_one()
    assert graded_in_current == 0


def test_users_reference_valid_identities(tmp_path):
    engine = _fresh_engine(tmp_path, "users.db")
    with session_scope(engine) as s:
        generate(s, SMALL)
    with session_scope(engine) as s:
        users = s.execute(select(User)).scalars().all()
    for user in users:
        if user.role == "student":
            assert user.student_id is not None and user.teacher_id is None
        else:
            assert user.teacher_id is not None and user.student_id is None
