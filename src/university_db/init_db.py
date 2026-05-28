"""Initialize a database: reset, apply the authoritative schema, then seed.

CLI entrypoint (see [project.scripts]):
    university-init-db [--db-url URL] [--no-seed]
"""

from __future__ import annotations

import argparse

from university_db.engine import make_engine, resolve_db_url, session_scope
from university_db.models import Base
from university_db.schema import apply_schema
from university_db.seed import generate


def init_db(db_url: str | None = None, *, seed: bool = True) -> dict[str, int]:
    """Drop existing tables, apply schema.sql, optionally seed. Returns row counts."""
    engine = make_engine(db_url, read_only=False)
    Base.metadata.drop_all(engine)  # idempotent reset so init is re-runnable
    apply_schema(engine)
    if not seed:
        return {}
    with session_scope(engine) as session:
        return generate(session)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the university database.")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy URL (default: env or sqlite)")
    parser.add_argument("--no-seed", action="store_true", help="Apply schema only; skip seeding")
    args = parser.parse_args()

    counts = init_db(args.db_url, seed=not args.no_seed)
    print(f"Initialized {resolve_db_url(args.db_url)}")
    for table, count in counts.items():
        print(f"  {table:18} {count}")


if __name__ == "__main__":
    main()
