"""Smoke test: package is importable and CI is wired."""

import university_agent


def test_package_imports():
    assert university_agent.__version__ == "0.1.0"
