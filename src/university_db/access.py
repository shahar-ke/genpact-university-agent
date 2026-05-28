"""Per-user data-access scoping (row-level security substrate).

Resolves a username to a Scope: their role, identity, the set of relations they may
query, and the SQL defining their session-scoped views. The agent only ever sees these
scoped views plus public reference tables; the MCP executor rejects any query that
references a relation outside the scope's allowlist.

Lives in university_db (not the MCP server) so it is unit-testable without MCP, and so
all knowledge of the schema stays in the DB package.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select
from sqlalchemy.orm import Session

from university_db.models import User
from university_db.roles import Role

# Reference relations any authenticated user may read: no per-user PII or grades.
PUBLIC_RELATIONS: tuple[str, ...] = ("courses", "semesters", "course_offerings", "teachers")

# Every domain table an admin may read directly. Excludes `users` (auth metadata, not data).
ADMIN_RELATIONS: tuple[str, ...] = (
    "students",
    "teachers",
    "courses",
    "semesters",
    "course_offerings",
    "enrollments",
)


@dataclass(frozen=True)
class Scope:
    """What a single authenticated user may query.

    allowlist is the set of relation names the executor permits (public tables plus the
    user's own views); view_sql maps each scoped view name to the SELECT defining it.
    """

    username: str
    role: Role
    entity_id: int | None  # students.id / teachers.id; None for admin (no bound entity)
    allowlist: frozenset[str]
    view_sql: dict[str, str]


def resolve_scope(session: Session, username: str) -> Scope | None:
    """Resolve a username to its Scope via the users table; None if the user is unknown."""
    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        return None
    return _build_scope(username, user.role, user.student_id, user.teacher_id)


def _build_scope(username: str, role: str, student_id: int | None, teacher_id: int | None) -> Scope:
    """Dispatch to the role-specific scope builder; raise on an unsupported role.

    The users table CHECK already constrains role to the supported set, so the raise is
    defense against schema drift rather than a reachable path in normal operation.
    """
    if role == Role.STUDENT:
        assert student_id is not None  # guaranteed by the users CHECK constraint
        return _student_scope(username, student_id)
    if role == Role.TEACHER:
        assert teacher_id is not None
        return _teacher_scope(username, teacher_id)
    if role == Role.ADMIN:
        return _admin_scope(username)
    raise ValueError(
        f"Unsupported role {role!r} for user {username!r}; "
        f"expected one of {[r.value for r in Role]}."
    )


def _scope(username: str, role: Role, entity_id: int, views: dict[str, str]) -> Scope:
    """Assemble a Scope whose allowlist is the public relations plus the given view names."""
    return Scope(
        username=username,
        role=role,
        entity_id=entity_id,
        allowlist=frozenset(PUBLIC_RELATIONS).union(views.keys()),
        view_sql=views,
    )


def _admin_scope(username: str) -> Scope:
    """Admin reads every domain table directly: no scoping views, no bound entity."""
    return Scope(
        username=username,
        role=Role.ADMIN,
        entity_id=None,
        allowlist=frozenset(ADMIN_RELATIONS),
        view_sql={},
    )


# noinspection SqlNoDataSourceInspection
def _student_scope(username: str, student_id: int) -> Scope:
    """Scope a student to their own enrollments (`my_enrollments`) and profile (`me`)."""
    # entity_id is a trusted integer from the users table, not free user input.
    sid = int(student_id)
    views = {
        "my_enrollments": f"SELECT * FROM enrollments WHERE student_id = {sid}",
        "me": f"SELECT id, name, email FROM students WHERE id = {sid}",
    }
    return _scope(username, Role.STUDENT, sid, views)


# noinspection SqlNoDataSourceInspection
def _teacher_scope(username: str, teacher_id: int) -> Scope:
    """Scope a teacher to their own offerings, the enrollments in them, and those students."""
    tid = int(teacher_id)
    views = {
        "my_offerings": f"SELECT * FROM course_offerings WHERE teacher_id = {tid}",
        "my_enrollments": (
            "SELECT e.* FROM enrollments e "
            "JOIN course_offerings o ON e.offering_id = o.id "
            f"WHERE o.teacher_id = {tid}"
        ),
        "my_students": (
            "SELECT DISTINCT s.id, s.name, s.email FROM students s "
            "JOIN enrollments e ON e.student_id = s.id "
            "JOIN course_offerings o ON e.offering_id = o.id "
            f"WHERE o.teacher_id = {tid}"
        ),
    }
    return _scope(username, Role.TEACHER, tid, views)


def create_session_views(connection: Connection, scope: Scope) -> None:
    """Materialize the scope's views as TEMP views on this connection.

    TEMP views live in SQLite's per-connection temp schema, which stays writable even on
    a read-only (mode=ro) main database — so the agent's connection can be read-only for
    data while still setting up its scoped views.
    """
    for name, sql in scope.view_sql.items():
        connection.exec_driver_sql(f"CREATE TEMP VIEW IF NOT EXISTS {name} AS {sql}")
