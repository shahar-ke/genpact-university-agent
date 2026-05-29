"""User directory (mock-login) lookups."""

from university_db.directory import list_users_by_role
from university_db.engine import make_engine, session_scope
from university_db.models import Student, Teacher, User
from university_db.roles import Role
from university_db.schema import apply_schema


def _seed(engine):
    with session_scope(engine) as s:
        alice = Student(name="Alice", email="a@uni.edu")
        bob = Student(name="Bob", email="b@uni.edu")
        prof = Teacher(name="Prof", email="p@uni.edu")
        s.add_all([alice, bob, prof])
        s.flush()
        s.add_all(
            [
                User(username="alice", role="student", student_id=alice.id),
                User(username="bob", role="student", student_id=bob.id),
                User(username="prof", role="teacher", teacher_id=prof.id),
                User(username="admin", role="admin"),
            ]
        )


def test_lists_usernames_for_role(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'dir.db'}", read_only=False)
    apply_schema(engine)
    _seed(engine)

    assert list_users_by_role(engine, Role.STUDENT) == ["alice", "bob"]
    assert list_users_by_role(engine, Role.TEACHER) == ["prof"]
    assert list_users_by_role(engine, Role.ADMIN) == ["admin"]


def test_respects_limit(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'lim.db'}", read_only=False)
    apply_schema(engine)
    _seed(engine)

    assert list_users_by_role(engine, Role.STUDENT, limit=1) == ["alice"]
