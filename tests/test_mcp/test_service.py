"""MCP service logic: scoped query execution and schema description over a real DB."""

import pytest

from university_db.access import resolve_scope
from university_db.engine import make_engine, session_scope
from university_db.models import (
    Course,
    CourseOffering,
    Enrollment,
    Semester,
    Student,
    Teacher,
    User,
)
from university_db.schema import apply_schema
from university_db_mcp.service import (
    build_schema,
    query_for_user,
    run_query,
    schema_for_user,
)
from university_db_mcp.validation import RejectionCategory


# noinspection DuplicatedCode
def _seed_known(engine):
    """Alice (90) and Bob (60) in one offering taught by Prof; plus an admin login."""
    with session_scope(engine) as s:
        alice = Student(name="Alice", email="alice@uni.edu")
        bob = Student(name="Bob", email="bob@uni.edu")
        prof = Teacher(name="Prof", email="prof@uni.edu")
        course = Course(code="CS101", title="Intro")
        semester = Semester(term="Fall", year=2024)
        s.add_all([alice, bob, prof, course, semester])
        s.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=prof.id, semester_id=semester.id)
        s.add(offering)
        s.flush()
        s.add_all(
            [
                Enrollment(student_id=alice.id, offering_id=offering.id, grade=90.0),
                Enrollment(student_id=bob.id, offering_id=offering.id, grade=60.0),
                User(username="alice", role="student", student_id=alice.id),
                User(username="prof", role="teacher", teacher_id=prof.id),
                User(username="root", role="admin"),
            ]
        )


@pytest.fixture
def db(tmp_path):
    """A seeded database file; yields (read_only_engine, scope_resolver)."""
    rw = make_engine(f"sqlite:///{tmp_path / 'svc.db'}", read_only=False)
    apply_schema(rw)
    _seed_known(rw)
    ro = make_engine(f"sqlite:///{tmp_path / 'svc.db'}", read_only=True)

    def scope_for(username):
        with session_scope(rw) as s:
            return resolve_scope(s, username)

    return ro, scope_for


# noinspection PyTypeChecker
def test_student_query_returns_only_own_data(db):
    engine, scope_for = db
    result = run_query(scope_for("alice"), engine, "SELECT grade FROM my_enrollments")
    assert result["status"] == "ok"
    assert result["rows"] == [{"grade": 90.0}]  # Alice's, not Bob's


# noinspection PyTypeChecker
def test_forbidden_table_is_rejected(db):
    engine, scope_for = db
    result = run_query(scope_for("alice"), engine, "SELECT * FROM enrollments")
    assert result["status"] == "rejected"
    assert result["category"] == RejectionCategory.FORBIDDEN_RELATION


def test_non_select_is_rejected(db):
    engine, scope_for = db
    # noinspection PyTypeChecker
    result = run_query(scope_for("alice"), engine, "DROP TABLE courses")
    assert result["status"] == "rejected"
    assert result["category"] == RejectionCategory.NOT_READ_ONLY


# noinspection PyTypeChecker
def test_execution_error_is_returned_not_raised(db):
    engine, scope_for = db
    # passes shape + allowlist validation, but the column does not exist
    result = run_query(scope_for("alice"), engine, "SELECT bogus_col FROM my_enrollments")
    assert result["status"] == "error"
    assert "bogus_col" in result["reason"]


# noinspection PyTypeChecker
def test_duplicate_column_labels_are_disambiguated(db):
    engine, scope_for = db
    result = run_query(
        scope_for("alice"), engine, "SELECT student_id, student_id FROM my_enrollments"
    )
    assert result["status"] == "ok"
    assert result["columns"] == ["student_id", "student_id_2"]
    assert result["rows"][0]["student_id"] == result["rows"][0]["student_id_2"]


# noinspection PyTypeChecker
def test_teacher_sees_their_students(db):
    engine, scope_for = db
    result = run_query(scope_for("prof"), engine, "SELECT COUNT(*) AS n FROM my_students")
    assert result["status"] == "ok"
    assert result["rows"] == [{"n": 2}]


# noinspection PyTypeChecker
def test_admin_can_query_raw_tables(db):
    engine, scope_for = db
    result = run_query(scope_for("root"), engine, "SELECT COUNT(*) AS n FROM enrollments")
    assert result["status"] == "ok"
    assert result["rows"] == [{"n": 2}]


# noinspection PyTypeChecker
def test_schema_lists_scoped_relations_only(db):
    engine, scope_for = db
    schema = build_schema(scope_for("alice"), engine)
    names = {relation.name for relation in schema.relations}
    assert {"my_enrollments", "courses"} <= names
    # raw sensitive tables must not be described to a student
    assert {"users", "students", "enrollments"}.isdisjoint(names)
    # columns are populated and structured
    my_enrollments = next(r for r in schema.relations if r.name == "my_enrollments")
    assert {"grade", "student_id"} <= {c.name for c in my_enrollments.columns}


# ── Identity-per-call entry points (resolve scope from username) ────────────────


def test_query_for_user_resolves_scope_and_runs(db):
    engine, _ = db
    result = query_for_user(engine, "alice", "SELECT grade FROM my_enrollments")
    assert result["status"] == "ok"
    assert result["rows"] == [{"grade": 90.0}]


def test_schema_for_user_resolves_scope(db):
    engine, _ = db
    schema = schema_for_user(engine, "prof")
    names = {relation.name for relation in schema.relations}
    assert "my_students" in names


def test_unknown_user_raises(db):
    engine, _ = db
    with pytest.raises(ValueError, match="unknown user"):
        query_for_user(engine, "ghost", "SELECT 1")
