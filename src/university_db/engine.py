"""Engine and session management for the university DB.

Single source of truth for how we connect:
- resolves the DB URL (explicit arg > DATABASE_URL env > sqlite default)
- enables SQLite foreign-key enforcement (off by default in SQLite)
- can open a SQLite database read-only (used by the agent's query path)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DB_URL = "sqlite:///./university.db"


def resolve_db_url(db_url: str | None = None) -> str:
    """Explicit arg wins, then DATABASE_URL, then the local SQLite default."""
    return db_url or os.environ.get("DATABASE_URL") or DEFAULT_DB_URL


def _to_sqlite_readonly(url: str) -> str:
    """Rewrite a file-based SQLite URL into an OS-level read-only URI.

    sqlite:///./university.db -> sqlite:///file:./university.db?mode=ro&uri=true

    Read-only at the connection level cannot be toggled off by SQL (unlike
    PRAGMA query_only), so it is a hard guarantee for the agent's query path.
    In-memory and already-URI databases are left untouched.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix) :]
    if path.startswith("file:") or ":memory:" in path:
        return url
    return f"{prefix}file:{path}?mode=ro&uri=true"


def _register_sqlite_fk_pragma(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()


def make_engine(
    db_url: str | None = None,
    *,
    read_only: bool,
    echo: bool = False,
) -> Engine:
    """Create an engine for the resolved DB URL.

    `read_only` is a required keyword: every caller must state intent. This avoids a
    silent fail-open on the security-critical agent path (a forgotten flag would
    otherwise hand it a writable connection). Setup writers pass read_only=False;
    the agent query path passes read_only=True.

    read_only currently applies to SQLite file databases (the home-task backend);
    for other dialects it is a no-op here and would be enforced via DB roles.
    """
    url = resolve_db_url(db_url)
    is_sqlite = url.startswith("sqlite")

    if read_only and is_sqlite:
        url = _to_sqlite_readonly(url)

    engine = create_engine(url, echo=echo)

    if is_sqlite:
        _register_sqlite_fk_pragma(engine)

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional session: commit on success, roll back on error, always close."""
    session = make_session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
