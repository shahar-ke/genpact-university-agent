# university_db_mcp

A **FastMCP server** (stdio) — the *only* component with database access. It exposes a small,
scope-aware tool surface and validates every query before it reaches SQLite. A thin facade over
[university_db](../university_db/README.md); the agent talks to it as an MCP client.

## What it does

- **Identity-per-call** — the server is identity-stateless. Each call carries a `user_id`, so a
  single instance serves all users and is discovered once at startup (no per-user subprocess).
  The same code would work unchanged over an HTTP transport for a multi-user deployment.
- **Security invariant** — `user_id` is supplied by the *trusted agent* from the authenticated
  session, **never by the LLM** (which only ever generates `sql`). The server resolves that
  user's `Scope` (from `university_db.access`) and runs everything within it.

## Tools & resource

| Surface | Kind | Role |
|---|---|---|
| `get_accessible_schema(user_id)` | tool | the relations + columns the user may query (introspected live, never hardcoded) |
| `execute_sql(user_id, sql)` | tool | validate then run read-only SQL within the user's scope; returns a structured result |
| `db://examples` | resource | few-shot example queries (incl. the window-function percentile pattern, since SQLite lacks `PERCENTILE_CONT`) |

`execute_sql` always returns a structured outcome the agent can route on, never raising on bad
SQL: `rejected` (failed validation, with category + reason), `error` (valid but failed at
execution, e.g. a bad column), or `ok` (columns + row_count + rows). Both rejection and error
are normal, self-correctable outcomes.

## Design / key files

| File | Role |
|---|---|
| `server.py` | FastMCP wrapper: lifespan builds one shared read-only engine; tools resolve scope and delegate |
| `service.py` | the real logic as plain functions (no MCP plumbing → directly unit-testable): scope-aware schema description + query execution |
| `validation.py` | sqlglot-based gate — runs *before* execution, never executes |

**Defense in depth.** Three independent layers make leaks impossible regardless of what the LLM
generates: (1) the SQL validator — exactly one statement, read-only `SELECT`/set-op only, and
every referenced relation within the caller's allowlist; (2) per-user scoped TEMP views so raw
sensitive tables aren't even named; (3) an OS-level read-only connection (from `university_db`)
that SQL cannot toggle off.

## Main libraries

| Library | Why |
|---|---|
| **mcp** / **FastMCP** | the MCP server over stdio (tools + resource) |
| **sqlglot** | AST-based SQL validation (dialect-aware, read-only + allowlist checks) |
| **SQLAlchemy 2.0** | the read-only engine and query execution (via `university_db`) |

Installed via the `db-mcp` extra (`uv sync --extra db-mcp`).
