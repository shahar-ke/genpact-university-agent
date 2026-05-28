"""Engine behavior: URL resolution and read-only enforcement (the security base layer)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from university_db.engine import DEFAULT_DB_URL, make_engine, resolve_db_url
from university_db.schema import apply_schema


def test_resolve_db_url_precedence(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_db_url("sqlite:///explicit.db") == "sqlite:///explicit.db"
    assert resolve_db_url() == DEFAULT_DB_URL

    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")
    assert resolve_db_url() == "sqlite:///env.db"
    assert resolve_db_url("sqlite:///explicit.db") == "sqlite:///explicit.db"  # explicit still wins


def test_read_only_connection_rejects_writes(tmp_path):
    db = tmp_path / "ro.db"
    # read-only SQLite needs an existing file, so create it with a writable engine first.
    apply_schema(make_engine(f"sqlite:///{db}", read_only=False))

    ro = make_engine(f"sqlite:///{db}", read_only=True)
    with pytest.raises(OperationalError), ro.begin() as conn:
        conn.execute(text("INSERT INTO students (name, email) VALUES ('x', 'x@y.z')"))


def test_read_only_connection_allows_reads(tmp_path):
    db = tmp_path / "ro2.db"
    rw = make_engine(f"sqlite:///{db}", read_only=False)
    apply_schema(rw)
    with rw.begin() as conn:
        conn.execute(text("INSERT INTO students (name, email) VALUES ('Ann', 'ann@y.z')"))

    ro = make_engine(f"sqlite:///{db}", read_only=True)
    with ro.connect() as conn:
        rows = conn.execute(text("SELECT name FROM students")).all()
    assert rows == [("Ann",)]
