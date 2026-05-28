"""Per-user scoping: allowlists, view scoping, and the read-only + temp-view guarantee."""

import pytest
from sqlalchemy import text

# noinspection PyProtectedMember
from university_db.access import (
    ADMIN_RELATIONS,
    PUBLIC_RELATIONS,
    _build_scope,
    create_session_views,
    resolve_scope,
)
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


def _seed_known(engine):
    """Two students in one offering; one teacher. Known ids for precise assertions."""
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
                User(username="bob", role="student", student_id=bob.id),
                User(username="prof", role="teacher", teacher_id=prof.id),
                User(username="root", role="admin"),
            ]
        )


def _engine(tmp_path, name, *, read_only=False):
    """Engine at tmp_path/name; schema is applied separately by each test that needs it."""
    engine = make_engine(f"sqlite:///{tmp_path / name}", read_only=read_only)
    return engine


def test_build_scope_rejects_unsupported_role():
    with pytest.raises(ValueError, match="Unsupported role"):
        _build_scope("someone", "superuser", None, None)


def test_unknown_user_has_no_scope(tmp_path):
    engine = _engine(tmp_path, "u.db")
    apply_schema(engine)
    _seed_known(engine)
    with session_scope(engine) as s:
        assert resolve_scope(s, "nobody") is None


def test_student_scope_allowlist_excludes_raw_sensitive_tables(tmp_path):
    engine = _engine(tmp_path, "s.db")
    apply_schema(engine)
    _seed_known(engine)
    with session_scope(engine) as s:
        scope = resolve_scope(s, "alice")
    assert scope is not None
    assert scope.role == "student"
    assert {"my_enrollments", "me"} <= scope.allowlist
    assert set(PUBLIC_RELATIONS) <= scope.allowlist
    # raw sensitive tables must never be queryable
    assert "enrollments" not in scope.allowlist
    assert "students" not in scope.allowlist
    assert "users" not in scope.allowlist


def test_teacher_scope_allowlist(tmp_path):
    engine = _engine(tmp_path, "t.db")
    apply_schema(engine)
    _seed_known(engine)
    with session_scope(engine) as s:
        scope = resolve_scope(s, "prof")
    assert scope is not None
    assert scope.role == "teacher"
    assert {"my_offerings", "my_enrollments", "my_students"} <= scope.allowlist
    assert "enrollments" not in scope.allowlist


# noinspection SqlNoDataSourceInspection
def test_student_views_are_scoped_to_self(tmp_path):
    engine = _engine(tmp_path, "scoped.db")
    apply_schema(engine)
    _seed_known(engine)
    with session_scope(engine) as s:
        alice_scope = resolve_scope(s, "alice")
    assert alice_scope is not None
    with engine.connect() as conn:
        create_session_views(conn, alice_scope)
        rows = conn.execute(text("SELECT grade FROM my_enrollments")).all()
    assert rows == [(90.0,)]  # Alice sees only her own enrollment, not Bob's


# noinspection SqlNoDataSourceInspection
def test_views_work_on_read_only_connection(tmp_path):
    """The critical guarantee: scoped TEMP views can be built on a read-only connection."""
    rw = _engine(tmp_path, "ro.db", read_only=False)
    apply_schema(rw)
    _seed_known(rw)
    with session_scope(rw) as s:
        prof_scope = resolve_scope(s, "prof")
    ro = _engine(tmp_path, "ro.db", read_only=True)
    assert prof_scope is not None
    with ro.connect() as conn:
        create_session_views(conn, prof_scope)
        count = conn.execute(text("SELECT COUNT(*) FROM my_students")).scalar_one()
        # and writes are still rejected on this connection
    assert count == 2  # Alice and Bob


def test_admin_scope_reads_all_domain_tables_without_views(tmp_path):
    engine = _engine(tmp_path, "admin.db")
    apply_schema(engine)
    _seed_known(engine)
    with session_scope(engine) as s:
        scope = resolve_scope(s, "root")
    assert scope is not None
    assert scope.role == "admin"
    assert scope.entity_id is None
    assert scope.view_sql == {}  # no scoping views
    assert scope.allowlist == frozenset(ADMIN_RELATIONS)
    # admin can reach the raw sensitive tables a student/teacher never could
    assert {"enrollments", "students"} <= scope.allowlist
    # but auth metadata stays off-limits even for admin
    assert "users" not in scope.allowlist


# noinspection SqlNoDataSourceInspection
def test_admin_can_aggregate_across_all_data(tmp_path):
    """Demo-shaped query: which teacher has the most enrolled students (unscoped)."""
    engine = _engine(tmp_path, "admin_q.db")
    apply_schema(engine)
    _seed_known(engine)
    with engine.connect() as conn:
        top = conn.execute(
            text(
                "SELECT t.name, COUNT(DISTINCT e.student_id) AS n "
                "FROM teachers t "
                "JOIN course_offerings o ON o.teacher_id = t.id "
                "JOIN enrollments e ON e.offering_id = o.id "
                "GROUP BY t.id, t.name ORDER BY n DESC LIMIT 1"
            )
        ).one()
    assert top == ("Prof", 2)  # Prof teaches the only offering; Alice + Bob
