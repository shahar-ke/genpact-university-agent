"""Core MCP service logic: scope-aware schema description and query execution.

Plain functions with no MCP plumbing, so they are unit-testable directly. server.py is a
thin FastMCP wrapper that resolves the caller's scope and delegates here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text

from university_db.access import Scope, create_session_views, resolve_scope
from university_db.engine import session_scope
from university_db_mcp.validation import validate_sql


@dataclass(frozen=True)
class ColumnInfo:
    """One column of a relation: its name and SQLite declared type."""

    name: str
    type: str  # SQLite declared type; may be empty for view columns


@dataclass(frozen=True)
class RelationInfo:
    """A queryable relation (table or scoped view) and its columns."""

    name: str
    columns: list[ColumnInfo]


@dataclass(frozen=True)
class AccessibleSchema:
    """The relations (scoped views + public/admin tables) a user may query.

    Role itself is intentionally not returned: it is server-side machinery used to compute
    these relations, and the client neither needs nor enforces it.
    """

    relations: list[RelationInfo]


# Few-shot examples surfaced as an MCP resource to steer SQL generation. Includes the
# window-function pattern for percentiles, since SQLite has no PERCENTILE_CONT aggregate.
EXAMPLE_QUERIES = """\
-- Average grade in a course (join scoped enrollments to the public catalog):
SELECT AVG(e.grade) FROM my_enrollments e
JOIN course_offerings o ON e.offering_id = o.id
JOIN courses c ON o.course_id = c.id
WHERE c.code = 'CS101';

-- 75th percentile grade (SQLite has no PERCENTILE_CONT; use a window function):
WITH g AS (
  SELECT grade, PERCENT_RANK() OVER (ORDER BY grade) AS pr
  FROM my_enrollments WHERE grade IS NOT NULL
)
SELECT MIN(grade) FROM g WHERE pr >= 0.75;
"""


# ── Identity-per-call entry points ─────────────────────────────────────────────
# The server is identity-stateless: each call carries the user_id, so one shared server
# serves all users. user_id is supplied by the trusted agent (the authenticated session),
# never by the LLM.


def query_for_user(engine: Engine, username: str, sql: str) -> dict[str, Any]:
    """Resolve the user's scope, then validate + execute the SQL within it."""
    return run_query(_resolve(engine, username), engine, sql)


def schema_for_user(engine: Engine, username: str) -> AccessibleSchema:
    """Resolve the user's scope, then describe the relations they may query."""
    return build_schema(_resolve(engine, username), engine)


def _resolve(engine: Engine, username: str) -> Scope:
    """Resolve a username to its Scope; raise if the (agent-supplied) identity is unknown.

    PRODUCTION: cache the resolved scope per user here (LRU/TTL or Redis) to avoid a DB
    lookup on every call.
    """
    with session_scope(engine) as session:
        scope = resolve_scope(session, username)
    if scope is None:
        raise ValueError(f"unknown user {username!r}")
    return scope


def run_query(scope: Scope, engine: Engine, sql: str) -> dict[str, Any]:
    """Validate then execute read-only SQL within the caller's scope.

    Returns a structured result the agent can route on: a rejection (category + reason) for
    invalid/out-of-scope SQL, or the result rows. Never raises on bad SQL — rejection is a
    normal, self-correctable outcome.
    """
    verdict = validate_sql(sql, scope.allowlist)
    if not verdict.ok:
        return {"status": "rejected", "category": verdict.category, "reason": verdict.reason}

    # Fresh connection per call: scoped TEMP views are connection-local, so this also rules
    # out cross-user view leakage if the engine's pool is ever shared (see server.py notes).
    with engine.connect() as conn:
        create_session_views(conn, scope)
        cursor = conn.execute(text(sql))
        columns = list(cursor.keys())
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    return {"status": "ok", "columns": columns, "row_count": len(rows), "rows": rows}


def build_schema(scope: Scope, engine: Engine) -> AccessibleSchema:
    """Describe every relation the caller may query (scoped views + public/admin tables).

    Schema-agnostic: columns are introspected from the live relations, not hardcoded. Raw
    sensitive tables never appear because they are not in the scope's allowlist.
    """
    with engine.connect() as conn:
        create_session_views(conn, scope)
        relations = [
            RelationInfo(name=relation, columns=_columns(conn, relation))
            for relation in sorted(scope.allowlist)
        ]
    return AccessibleSchema(relations=relations)


def _columns(conn: Connection, relation: str) -> list[ColumnInfo]:
    """Columns of a table or view. relation is a trusted name from the allowlist."""
    # PRAGMA table_info works for tables and views; row[1] is the name, row[2] the type.
    rows = conn.exec_driver_sql(f"PRAGMA table_info({relation})").fetchall()
    return [ColumnInfo(name=row[1], type=row[2]) for row in rows]
