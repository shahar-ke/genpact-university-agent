"""Apply the authoritative DDL (ddl/schema.sql) to a database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

_SCHEMA_PATH = Path(__file__).parent / "ddl" / "schema.sql"


def read_schema_sql() -> str:
    """Return the contents of the authoritative ddl/schema.sql file."""
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def apply_schema(engine: Engine) -> None:
    """Execute schema.sql against the engine.

    Uses SQLite's executescript for multi-statement DDL. The connect-time FK
    pragma (see engine.py) fires here because raw_connection() goes through the pool.
    """
    sql = read_schema_sql()
    raw = engine.raw_connection()
    try:
        raw.executescript(sql)  # SQLite-specific; fine for the home-task backend
        raw.commit()
    finally:
        raw.close()
