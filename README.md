# University QA Agent

A LangGraph agent that answers natural-language questions about a university database. It
translates a question into SQL, runs it through a row-level-secured MCP server, and returns a
human-readable answer — with per-user access control, self-correction, and full tracing.

Built for the [home task](<./HW Task.html.pdf>).

## Project structure

Six components, each with its own in-depth README (design, key files, libraries):

- [src/university_db/](src/university_db/README.md) — owns the university data (courses, people,
  enrollments, grades) and the rules for who may see what: a student sees only their own record,
  a teacher their classes, an admin everything.
- [src/university_db_mcp/](src/university_db_mcp/README.md) — the guarded gateway to that data.
  The only component allowed to touch the database; it enforces each user's access boundary and
  refuses anything unsafe.
- [src/university_agent/](src/university_agent/README.md) — the brains. Turns a plain-English
  question into an answer: judges whether it's in scope, fetches the data through the gateway,
  and self-corrects if a query fails.
- [src/university_cli/](src/university_cli/README.md) — one of two ways to use it: a terminal
  front end. Log in as a sample user and ask questions one at a time.
- [src/university_web/](src/university_web/README.md) — the other way to use it: a Streamlit web
  app over the same agent. A scoped query tool (role → user → question → answer + SQL + rows +
  trace) plus a filterable god-mode data browser for validating answers.
- [evals/](evals/README.md) — quality measurement. A fixed test set that scores how well
  different models answer the right questions and decline the wrong ones, so changes can be
  compared.

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — manages the Python environment and dependencies.
- **Python 3.11+**.
- **An LLM provider.** Pick one:
  - **Local (default) — [Ollama](https://ollama.com/).** Free, no API key, runs on your machine.
    Install it (see the [download page](https://ollama.com/download) and
    [docs](https://github.com/ollama/ollama/blob/main/README.md)), then start the server and pull
    the default model:
    ```bash
    ollama serve            # start the local server (skip if it already runs as a service)
    ollama pull gemma2:9b   # the default model
    ```
  - **Commercial (optional) — Anthropic or OpenAI.** No Ollama needed. Install the provider
    package and select it in `.env` (see [Installation](#installation)); the values below are
    what enable the commercial path:
    ```bash
    uv pip install langchain-anthropic   # or: langchain-openai
    ```
    ```dotenv
    # .env
    LLM_PROVIDER=anthropic
    LLM_MODEL=claude-sonnet-4-6
    ANTHROPIC_API_KEY=sk-ant-...         # or OPENAI_API_KEY for OpenAI
    ```

## Installation

```bash
uv sync --extra all --group dev                                 # full local install
cp .env.example .env                                            # configure LLM (+ optional LangSmith)
uv run university-init-db --db-url "sqlite:///./university.db"   # create + seed the database
```

`.env` is loaded automatically and is where you choose the LLM: it ships set to the local Ollama
default (`LLM_PROVIDER=ollama`, `LLM_MODEL=gemma2:9b`). To switch to a commercial model, set
`LLM_PROVIDER` / `LLM_MODEL` and the matching API key per [Prerequisites](#prerequisites).

### Loading data: fixed vs. generated
- **Fixed (canonical)** — `evals/fixture.sql` is a committed SQL dump: the same bytes on every
  machine, independent of seed logic or library versions. The eval and the web app's "fixed"
  option load it. Use it when answers must be verifiable against a known dataset.
- **Generated** — `university-init-db` (and `seed.py`'s `generate(SeedConfig(...))`) build a fresh
  dataset of a chosen size. It's seeded (reproducible within one environment) but exact values
  follow the installed Faker version — so it's for new/larger data, not a cross-machine reference.

## Usage

Two front ends over the same agent — a terminal CLI and a Streamlit web app.

### CLI
Ask one question and exit (fully specified — no prompts):
```bash
uv run university-agent-cli --user admin --question "which teacher has the most enrolled students?"
```
Run it with no flags for interactive mode — pick a role, then a user, then ask questions one at
a time (`--role` / `--user` skip the matching prompts):
```bash
uv run university-agent-cli
```

### Web app (demo & validation)
A Streamlit UI with two pages: a **Data view** (read-only, god-mode browser with per-column
sort + filter, for validating answers against ground truth) and a **Query tool** (the scoped
agent path: pick role → user → ask → see answer, generated SQL, result rows, and trace link).
Load the working DB from the fixed fixture or a fresh seed via the sidebar.

```bash
uv sync --extra web          # install the web deps (Streamlit + Ag-Grid)
uv run university-agent-web   # launch (or: uv run streamlit run src/university_web/app.py)
```

### Tracing (LangSmith)
Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`. Every run is traced end to end
(User → nodes → SQL → DB results → answer), tagged with the user/role; the CLI prints a link to
each question's trace.

### Execution traces (committed artifact)
Capture the agent's per-node flow (question → reasoning → SQL → rows → answer) over the fixed
fixture, as committed JSON under `traces/` — a flow artifact, independent of CLI vs. web:
```bash
uv run python -m evals.capture_traces                  # local capture (works without a key)
uv run python -m evals.capture_traces --from-langsmith # export full LangSmith run trees (needs a key)
```

### Tests & lint
```bash
uv run pytest          # full suite
uv run ruff check . && uv run ruff format --check .
```

### Evaluation
```bash
ollama pull llama3.1:8b                       # + ANTHROPIC_API_KEY / OPENAI_API_KEY in .env
uv run python -m evals.run_eval               # writes evals/report.md (per-topic + total per model)
```

## How it works

```
User question
  → LangGraph agent   (understand → generate SQL → execute → synthesize)
      → MCP server     (the only component with DB access; scope-enforced, read-only)
          → SQLite     (per-user TEMP views)
```

The agent never touches the database or SQL libraries directly — it talks to an MCP server
over JSON-RPC and discovers its tools. Identity is resolved **server-side**: a student sees
only their own enrollments, a teacher their courses, an admin everything. The LLM never sees
the user id, and a SQL validator (single read-only `SELECT` + table allowlist) plus a
read-only connection make data leaks impossible regardless of what the model generates.

## Home Task Deliverables

Jump to the answer for each required deliverable:

1. [SQL schema and seed data](#1-sql-schema-and-seed-data)
2. [LangGraph application code](#2-langgraph-application-code)
3. [Unit tests](#3-unit-tests)

### 1. SQL schema and seed data
`src/university_db/ddl/schema.sql` is the authoritative DDL — 7 tables (`students`, `teachers`,
`courses`, `semesters`, `course_offerings`, `enrollments`, `users`) with FK / UNIQUE / CHECK
constraints. The SQLAlchemy models in `models.py` mirror it, and a test applies the SQL then
exercises the models, so any drift fails the suite. Two data paths: **generate** a seeded dataset
via `university-init-db` / `seed.py` (size via `SeedConfig`), or **load the fixed** committed dump
`evals/fixture.sql` — see [Loading data: fixed vs. generated](#loading-data-fixed-vs-generated).

### 2. LangGraph application code
`src/university_agent/` (graph, nodes, state, LLM factory, MCP gateway) implements the pipeline
`understand → generate_sql → execute → synthesize`, with an off-topic / compound gate and capped
self-correction. It reaches the database only through the MCP server in `src/university_db_mcp/` —
the DB-agnostic boundary (the agent has no DB import, enforced by CI). Aggregations, joins,
filtering, and multi-step (CTE / window) queries are supported and exercised by the eval.

### 3. Unit tests
`tests/` (~63 tests, ~91% coverage): `test_db/` (schema↔models drift, FK/CHECK, read-only, seed
determinism, access scoping), `test_mcp/` (SQL validation, scoped execution + schema),
`test_agent/` (graph: happy / off-topic / unanswerable / retry / give-up / compound; node helpers;
LLM factory), `test_cli/`, and `test_e2e/` (real MCP server + DB, stubbed LLM). CI runs a
per-component matrix that also enforces the agent↔DB isolation. This covers the task's three named
areas: DB queries & joins, NL→SQL generation, and end-to-end agent behavior.
