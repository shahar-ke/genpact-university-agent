"""SQL validation stage for the execute_sql tool.

A deterministic gate between the agent's generated SQL and the database. It does NOT
execute anything — it parses the SQL with sqlglot and returns a structured verdict so the
agent's graph can route on rejections and self-correct.

Two independent checks:
1. shape  — exactly one statement, and it must be read-only (SELECT / set-operation).
2. access — every referenced table or view is within the caller's allowlist.

This sits above the read-only connection as defense in depth: it blocks writes and
out-of-scope reads before they ever reach SQLite, and gives the agent a reason it can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import sqlglot
from sqlglot import exp

DIALECT = "sqlite"

# Statement roots that only read: a SELECT, or a set-operation over SELECTs
# (UNION / INTERSECT / EXCEPT, which subclass exp.Union in sqlglot).
_READ_ONLY_ROOTS: tuple[type[exp.Expression], ...] = (exp.Select, exp.Union)


class RejectionCategory(StrEnum):
    """Why a SQL string was rejected; lets the agent route on the specific failure."""

    PARSE_ERROR = "parse_error"
    NOT_SINGLE_STATEMENT = "not_single_statement"
    NOT_READ_ONLY = "not_read_only"
    FORBIDDEN_RELATION = "forbidden_relation"


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one SQL string. Structured so the agent can route on it."""

    ok: bool
    category: RejectionCategory | None = None
    reason: str | None = None

    @classmethod
    def accept(cls) -> ValidationResult:
        """A passing result (ok=True, no category or reason)."""
        return cls(ok=True)

    @classmethod
    def reject(cls, category: RejectionCategory, reason: str) -> ValidationResult:
        """A failing result tagged with its category and a human-readable reason."""
        return cls(ok=False, category=category, reason=reason)


def validate_sql(sql: str, allowlist: frozenset[str]) -> ValidationResult:
    """Validate generated SQL against the shape and access rules; never executes it."""
    statements = _parse(sql)
    if statements is None:
        return ValidationResult.reject(RejectionCategory.PARSE_ERROR, "could not parse SQL")
    if len(statements) != 1:
        return ValidationResult.reject(
            RejectionCategory.NOT_SINGLE_STATEMENT,
            f"expected exactly one statement, got {len(statements)}",
        )

    statement = statements[0]
    if not isinstance(statement, _READ_ONLY_ROOTS):
        return ValidationResult.reject(
            RejectionCategory.NOT_READ_ONLY, "only read-only SELECT queries are allowed"
        )

    permitted = {name.lower() for name in allowlist}
    forbidden = _referenced_relations(statement) - permitted
    if forbidden:
        return ValidationResult.reject(
            RejectionCategory.FORBIDDEN_RELATION,
            f"query references relations outside your access scope: {sorted(forbidden)}",
        )
    return ValidationResult.accept()


def _parse(sql: str) -> list[exp.Expression] | None:
    """Parse into statements; None on syntax error. Empty statements are dropped."""
    try:
        parsed = sqlglot.parse(sql, dialect=DIALECT)
    except sqlglot.errors.ParseError:
        return None
    return [statement for statement in parsed if statement is not None]


def _referenced_relations(statement: exp.Expression) -> set[str]:
    """Lower-cased base tables/views referenced, excluding inline CTE names."""
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE)}
    tables = {table.name.lower() for table in statement.find_all(exp.Table)}
    return tables - cte_names
