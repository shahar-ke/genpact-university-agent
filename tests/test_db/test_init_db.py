"""init_db: apply schema then optionally seed, returning row counts."""

from university_db.init_db import init_db


def test_init_db_applies_schema_and_seeds(tmp_path):
    counts = init_db(f"sqlite:///{tmp_path / 'init.db'}", seed=True)
    assert counts["students"] > 0
    assert counts["users"] > 0
    assert counts["enrollments"] > 0


def test_init_db_schema_only_skips_seed(tmp_path):
    counts = init_db(f"sqlite:///{tmp_path / 'noseed.db'}", seed=False)
    assert counts == {}
