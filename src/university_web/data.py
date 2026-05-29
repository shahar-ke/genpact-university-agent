"""Working-database control + god-mode table reads (DB layer only, no agent).

One SQLite file backs the whole app. It is built either from the fixed eval fixture or
from a fresh deterministic seed, then handed to the agent (as db_url) and to the read-only
god-mode browser. This module imports only university_db — the agent never touches it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from university_db.engine import make_engine, session_scope
from university_db.models import Base
from university_db.schema import apply_schema
from university_db.seed import SeedConfig, generate

FIXTURE = Path(__file__).resolve().parents[2] / "evals" / "fixture.sql"

# The tables the god-mode browser exposes (validation view; not the scoped agent path).
TABLES: tuple[str, ...] = (
    "students",
    "teachers",
    "courses",
    "semesters",
    "course_offerings",
    "enrollments",
    "users",
)


def _load_fixture(db_path: Path) -> None:
    """Execute the self-contained fixture (schema + inserts) into a fresh SQLite file."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(FIXTURE.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


def _load_seed(db_url: str, config: SeedConfig) -> None:
    """Apply the authoritative schema then the deterministic Faker seed."""
    engine = make_engine(db_url, read_only=False)
    Base.metadata.drop_all(engine)
    apply_schema(engine)
    with session_scope(engine) as session:
        generate(session, config)


def build_db(db_path: Path, *, source: str, config: SeedConfig | None = None) -> dict[str, int]:
    """(Re)build the working DB from `source` ("fixture" or "seed"); return row counts.

    The file is removed first so a re-build always starts clean (the fixture's DDL has no
    IF NOT EXISTS, and switching sources must not leave stale tables behind).
    """
    db_path.unlink(missing_ok=True)
    db_url = f"sqlite:///{db_path}"
    if source == "fixture":
        _load_fixture(db_path)
    elif source == "seed":
        _load_seed(db_url, config or SeedConfig())
    else:
        raise ValueError(f"unknown source {source!r} (expected 'fixture' or 'seed')")
    return row_counts(db_url)


def row_counts(db_url: str) -> dict[str, int]:
    """Row count per table, via a read-only connection (matches the god-mode path)."""
    engine = make_engine(db_url, read_only=True)
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in TABLES}


def read_table(db_url: str, table: str) -> pd.DataFrame:
    """Read a whole table for the god-mode browser via a READ-ONLY engine.

    `table` is a fixed name from TABLES (not user input), so interpolation is safe.
    """
    engine = make_engine(db_url, read_only=True)
    with engine.connect() as conn:
        return pd.read_sql_query(text(f"SELECT * FROM {table}"), conn)
