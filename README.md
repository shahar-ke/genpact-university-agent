# University QA Agent

A LangGraph-based question-answering agent over a university SQL database. Translates natural-language questions into SQL, executes them, and returns human-readable answers.

> Technical home assignment.

## Status

Skeleton — implementation in progress.

## Stack

- **Python** 3.11+
- **LangGraph** — agent orchestration
- **SQL** (SQLite for local dev; portable to Postgres)
- **Pytest** — testing
- **Ruff** — lint + format

## Layout

```
src/university_agent/    # agent code
tests/                   # unit tests
.github/workflows/       # CI
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest
ruff check .
ruff format .
```
