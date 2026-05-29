"""Build the fixed eval dataset: seed a small deterministic DB, dump it to fixture.sql.

The dump is committed so the eval dataset is constant and inspectable. Re-run only when you
intend to change the eval data.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from university_db.engine import make_engine, session_scope
from university_db.schema import apply_schema
from university_db.seed import SeedConfig, generate

FIXTURE = Path(__file__).parent / "fixture.sql"
EVAL_CONFIG = SeedConfig(teachers=3, students=8, courses=6, semesters=3, retakes=2)


def main() -> None:
    """Seed a small deterministic DB from EVAL_CONFIG and dump it to fixture.sql."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval.db"
        engine = make_engine(f"sqlite:///{db_path}", read_only=False)
        apply_schema(engine)
        with session_scope(engine) as session:
            counts = generate(session, EVAL_CONFIG)
        engine.dispose()  # release the file before sqlite3 reopens it

        con = sqlite3.connect(db_path)
        FIXTURE.write_text("\n".join(con.iterdump()) + "\n", encoding="utf-8")
        con.close()
    print(f"Wrote {FIXTURE.name}: {counts}")


if __name__ == "__main__":
    main()
