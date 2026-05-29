# university_db

The data layer: SQLAlchemy schema/models, engine management, deterministic seeding, and the
per-user **access scoping** that the rest of the system builds on. It has no knowledge of MCP
or the agent — all schema knowledge lives here, and everything is unit-testable without them.

## What it does

- **Schema** — `ddl/schema.sql` is the authoritative DDL (applied at init time); `models.py`
  mirrors it as SQLAlchemy ORM models for typed seeding and queries. The test suite applies the
  DDL then exercises the models, so any drift between the two surfaces as a failure.
- **Engine** — `engine.py` is the single source of truth for connecting: resolves the DB URL
  (explicit arg > `DATABASE_URL` > sqlite default), enables SQLite FK enforcement on every
  connection, and can open a SQLite database **OS-level read-only** (`mode=ro`) — a hard
  guarantee SQL can't toggle off, used by the agent's query path. `read_only` is a required
  keyword so no caller silently fails open.
- **Access scoping** (`access.py`) — resolves a username to a `Scope`: their role, identity,
  the relation **allowlist** they may query, and the SQL defining their session-scoped views.
  Students see `my_enrollments` / `me`; teachers see `my_offerings` / `my_enrollments` /
  `my_students`; admins read domain tables directly. Views are materialized as per-connection
  **TEMP views** (writable even on a read-only main DB) and dropped+recreated each call to rule
  out cross-user leakage on a pooled connection. This is the row-level-security substrate the
  MCP server enforces.
- **Seeding** (`seed.py`) — Faker + a fixed seed produce a small, realistic, reproducible
  dataset (consistent student skill / course difficulty so aggregates are meaningful, a few
  retakes, the current term left ungraded). Scale is a `SeedConfig` parameter so tests can build
  tiny datasets.
- **Directory** (`directory.py`) — pre-auth username lookups for the demo's mock-login (a direct
  read, **not** part of the scoped query path).
- **Init** (`init_db.py`) — `university-init-db` CLI: reset, apply schema, optionally seed.

## Key files

| File | Role |
|---|---|
| `ddl/schema.sql` | authoritative DDL (the source of truth for the schema) |
| `models.py` | ORM models mirroring the DDL |
| `engine.py` | URL resolution, FK pragma, read-only connections, session scope |
| `access.py` | `Scope`, role-specific view definitions, TEMP-view materialization |
| `roles.py` | the `Role` `StrEnum` — single source of the role vocabulary |
| `seed.py` | deterministic Faker dataset generator |
| `directory.py` | mock-login user lookups |
| `schema.py` / `init_db.py` | apply DDL / init+seed CLI |

## Main libraries

| Library | Why |
|---|---|
| **SQLAlchemy 2.0** | engine, declarative models, sessions (SQLite now; portable to Postgres) |
| **Faker** | deterministic mock data (seeded for reproducibility) |

Installed via the `db` / `seed` extras (`uv sync --extra seed`).
