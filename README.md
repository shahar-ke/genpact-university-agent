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
uv run python -m evals.run_eval               # writes a per-topic + total report per model
uv run python -m evals.run_eval --only claude-sonnet --out evals/report.claude.md  # one model
```
The committed [`evals/leaderboard.md`](evals/leaderboard.md) is the stable summary (cases + model
leaderboard); the generated `report.<model>.md` files (git-ignored) hold the full per-case detail.

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

A user cannot access data they are not allowed to — enforced below the LLM, not left to it.
Though not called out in the brief, this drove much of the design; see
[DESIGN.md §1](DESIGN.md#1-a-user-must-never-see-data-which-they-are-not-allowed-to-see).

### Evaluation at a glance
Quality is measured by a fixed test set — **50 cases across 7 topics** (aggregation, filtering,
joins, multi_step, access_control, relevance, compound) over the committed `evals/fixture.sql`,
scored per-topic and total. The committed leaderboard is
[`evals/leaderboard.md`](evals/leaderboard.md):

| Model | Total | Notes |
|---|---|---|
| claude-sonnet (`claude-sonnet-4-6`) | 45/50 | near-perfect on the SQL topics |
| gpt-5.4-mini | 41/50 | fastest of the three |
| gemma2:9b (local) | 33/50 | strong on aggregation/filtering; weaker on joins / multi-step |

No model leaked data on any access-control case — scope is enforced server-side, so safety is
independent of model quality. Per-model, per-case detail lives in the generated `report.<model>.md`
files (regenerate with `python -m evals.run_eval`; see [Evaluation](#evaluation)).

## Home Task Deliverables

Jump to the answer for each required deliverable:

1. [SQL schema and seed data](#1-sql-schema-and-seed-data)
2. [LangGraph application code](#2-langgraph-application-code)
3. [Unit tests](#3-unit-tests)
4. [Documentation explaining design decisions](#4-documentation-explaining-design-decisions)
5. [Example queries and outputs](#5-example-queries-and-outputs)
6. [Execution traces](#6-execution-traces)
7. [Production considerations](#7-production-considerations)

### 1. SQL schema and seed data
`src/university_db/ddl/schema.sql` is the authoritative DDL — 7 tables (`students`, `teachers`,
`courses`, `semesters`, `course_offerings`, `enrollments`, `users`) with FK / UNIQUE / CHECK
constraints. It is the **contract**: a stable, deterministic surface the rest of the system is
written against. The backing implementation is free to change behind it — the same DDL runs on
SQLite today and could run on Postgres unchanged, the SQLAlchemy models in `models.py` mirror it
(a test applies the SQL then exercises the models, so any drift fails the suite), and the data
behind it can be swapped — without anything upstream noticing. Two data paths: **generate** a
seeded dataset via `university-init-db` / `seed.py` (size via `SeedConfig`), or **load the fixed**
committed dump `evals/fixture.sql` — see
[Loading data: fixed vs. generated](#loading-data-fixed-vs-generated).

### 2. LangGraph application code
`src/university_agent/` (graph, nodes, state, LLM factory, MCP gateway) implements the pipeline
`understand → generate_sql → execute → synthesize`, with an off-topic / compound gate and capped
self-correction. It reaches the database only through the MCP server in `src/university_db_mcp/` —
the DB-agnostic boundary (the agent has no DB import, enforced by CI). Aggregations, joins,
filtering, and multi-step (CTE / window) queries are supported and exercised by the eval.

### 3. Unit tests
~63 tests, ~91% coverage, mirroring the package layout — one test subpackage per component:

```
tests/
├── test_db/          # the data layer + its security base
│   ├── test_schema.py      apply the DDL then exercise the ORM — guards schema.sql ↔ models drift
│   ├── test_engine.py      URL resolution + read-only enforcement (the security base layer)
│   ├── test_access.py      per-user scoping: allowlists, TEMP views, read-only guarantee
│   ├── test_seed.py        seed generator: counts, determinism, data invariants
│   ├── test_directory.py   user directory (mock-login) lookups
│   └── test_init_db.py     apply schema then optionally seed, returning row counts
├── test_mcp/         # the guarded gateway
│   ├── test_validation.py  SQL validation: single read-only SELECT + table allowlist
│   └── test_service.py     scoped query execution + schema description over a real DB
├── test_agent/       # the LangGraph agent (fake LLM + fake gateway, no Ollama/MCP)
│   ├── test_graph.py       happy / off-topic / unanswerable / retry-then-succeed / give-up
│   ├── test_nodes.py       pure node helpers (no LLM / no gateway)
│   └── test_llm.py         make_llm builds the model from env without a real provider
├── test_cli/
│   └── test_app.py         CLI composition-root helpers (interactive I/O monkey-patched)
├── test_e2e/
│   └── test_end_to_end.py  real graph → real MCP subprocess → real SQLite (only LLM stubbed)
└── test_smoke.py           package imports + CI wiring
```

**Run in CI.** Every push / PR to `main` runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
a lint+format job (`ruff`) plus a **per-component test matrix** that installs *only* each
component's dependency footprint. This makes CI enforce the agent↔DB isolation — the `agent` leg
has no `sqlalchemy`, so an accidental DB import there fails the build.

**Run manually.**
```bash
uv run pytest                              # full suite
uv run pytest --cov=src --cov-report=term  # with coverage
uv run pytest tests/test_db -v             # one component
uv run pytest tests/test_agent/test_graph.py::test_off_topic_short_circuits  # one test
```

This covers the task's three named areas: DB queries & joins, NL→SQL generation, and end-to-end
agent behavior.

### 4. Documentation explaining design decisions
[`DESIGN.md`](DESIGN.md) walks through the architecture as it was actually decided: each section
starts from a **critical product/business concern** and derives the **technical decision** that
supports it — e.g. *"a user must never see data they are not allowed to see"* drove the deterministic, server-side
row-level security that sits below the LLM; *"the contract must stay stable while the implementation
changes"* drove `schema.sql` as the authoritative, portable contract. The per-component READMEs
linked under [Project structure](#project-structure) cover each module's local design, key files,
and libraries.

### 5. Example queries and outputs
The primary evidence is the **committed LangSmith trace exports** under
[`traces/langsmith/`](traces/langsmith) — full run trees captured end to end (User → graph nodes →
LLM calls → MCP/SQL → DB rows → answer) over the fixed `evals/fixture.sql`. Each is a complete,
inspectable record of a real run.

The three exported runs, each as *question → generated SQL → answer*. Note the scoping: a student's
schema exposes `my_enrollments` / `me` (already filtered to that user server-side), so the SQL needs
no `WHERE` on a user id.

**Student — "What is my average grade?"** (as `ddavis`) — [export](traces/langsmith/student_avg_grade.json)
```sql
SELECT AVG(grade) FROM my_enrollments WHERE grade IS NOT NULL
```
> The average grade of your enrollments is 81.07.

**Admin — "Which teacher has the most enrolled students?"** (aggregation over a 3-table join) — [export](traces/langsmith/admin_top_teacher.json)
```sql
SELECT t.name FROM teachers t
JOIN course_offerings co ON t.id = co.teacher_id
JOIN enrollments e ON co.id = e.offering_id
GROUP BY t.name
ORDER BY COUNT(e.id) DESC
LIMIT 1
```
> Allison Hill

**Teacher — "How many distinct students do I teach?"** (as `dcarlson`) — [export](traces/langsmith/teacher_distinct_students.json) — the **self-correction + graceful give-up** path: the local model's SQL failed validation/execution, the error was fed back across retries (visible in the trace), and the agent declined cleanly rather than fabricating.
> I couldn't form a valid query for that after several attempts. Last issue: no such column: t.name.

More example outputs:
- **[`evals/leaderboard.md`](evals/leaderboard.md)** — the committed eval summary (cases + model
  leaderboard). The generated `report.<model>.md` files add every one of the 50 cases as
  *question → agent SQL → answer*, scored against ground truth, including the off-topic /
  access-control declines (regenerate via [Evaluation](#evaluation)).
- **`traces/*.json`** — the compact per-node execution traces alongside the full LangSmith exports
  (see [Execution traces](#execution-traces-committed-artifact)).
- **`db://examples`** — the canonical sample queries the MCP server advertises to the agent.

### 6. Execution traces
Committed under [`traces/`](traces), produced by `evals.capture_traces` over the fixed
`evals/fixture.sql` (see [Execution traces](#execution-traces-committed-artifact) for how to
regenerate). Each run exists in **two forms**: a compact per-node flow
`traces/<name>.json` (question → reasoning → SQL → result rows → answer — works with no key), and
the full LangSmith run tree `traces/langsmith/<name>.json` (root graph run + every node + LLM/tool
child runs, with timing and token usage — exported via `--from-langsmith`).

Three runs, chosen to cover one role each and both the happy and self-correcting paths:

| Trace | Flow | LangSmith export | What it shows |
|---|---|---|---|
| `student_avg_grade` | [json](traces/student_avg_grade.json) | [json](traces/langsmith/student_avg_grade.json) | **Student**, happy path — scoped scalar aggregation (`AVG(grade)` over `my_enrollments`); no user-id filter needed because the view is pre-scoped. |
| `admin_top_teacher` | [json](traces/admin_top_teacher.json) | [json](traces/langsmith/admin_top_teacher.json) | **Admin**, happy path — aggregation over a 3-table join (`teachers`→`course_offerings`→`enrollments`) with `GROUP BY` / `ORDER BY` / `LIMIT`. |
| `teacher_distinct_students` | [json](traces/teacher_distinct_students.json) | [json](traces/langsmith/teacher_distinct_students.json) | **Teacher**, self-correction → graceful give-up — the model's SQL failed, the error was fed back across capped retries, and the agent declined cleanly instead of fabricating. |

### 7. Production considerations
What would change moving from this take-home to a real deployment. High level — the critical points
per area, not an implementation plan.

#### Reliability
The agent already fails safe: capped self-correction on bad SQL, graceful decline on
out-of-scope/unanswerable questions, and read-only access so no run can corrupt data. In production
the database itself becomes the reliability anchor — it should be a **managed engine** (e.g. managed
Postgres) with automated backups, point-in-time recovery, and a **disaster-recovery** posture:
multi-AZ replication, a tested restore runbook, and explicit RPO/RTO targets so a regional failure
is a known, rehearsed event rather than data loss. Around the agent, add timeouts and circuit
breakers on the LLM and MCP calls, bound result sizes, and keep runs idempotent/retryable. The
DB-agnostic MCP boundary is what makes this swap possible without touching agent code.

#### Scalability
The MCP server is stateless and identity-per-call (no per-user process), so it scales horizontally
behind a load balancer; the async agent replicates the same way, and read replicas absorb the query
load. The first real bottleneck is LLM inference, not the DB. Because answering a question is
multi-step and latency-tolerant, there is room for a **queue as a buffer**: accept a question, return
a handle, and have a pool of workers consume from the queue and push the answer back (web socket /
poll). That decouples request spikes from model throughput, smooths cost, gives natural back-pressure
and retry semantics, and lets the heavy inference tier scale independently of the front end — at the
price of an async UX, so it is best applied to the slow path (inference) rather than the fast
schema/validation steps, which stay synchronous. **Caching** is the other major lever and applies at
several layers: the per-user accessible schema and the `db://examples` lookups (stable, cheap to
cache per role); a semantic/exact cache on question → SQL so repeated or near-identical questions
skip the LLM entirely; and short-TTL caching of result sets for hot read-only queries. Caching cuts
both latency and inference cost, which is the dominant spend at scale — with per-user scoping
respected in the cache key so nothing leaks across users.

#### Monitoring & tracing
Two layers. **Online** (live ops): structured logs, RED metrics (rate/errors/duration) per node and
per MCP call, latency/cost/token dashboards, and alerts on retry-rate, give-up-rate, and decline-rate
as real-time quality signals. **Offline** (batch/quality): the fixed eval (50 cases, per-topic
scoring) as a CI quality gate on every model or prompt change, plus periodic replay of sampled real
traffic. On top of the technical metrics, track **business metrics** — daily active customers (DAC),
total sessions — and a lightweight **satisfaction signal** in the web app (a thumbs up/down per
answer) feeding a **feedback store reviewed by a dedicated agent** that clusters and triages it. A
useful product signal here is the **rate of similar/repeated queries from one user within a time
window**: a spike flags a user struggling to phrase what they want, and can trigger help or query
suggestions. Tracing (LangSmith end to end + committed JSON traces) is already wired and underpins
all of this.

#### Security
Access control is enforced server-side and independent of the model: per-user TEMP views +
read-only connection + SQL validation (single SELECT, table allowlist), with the LLM never seeing
the `user_id`. For production, put real authentication/authorization in front (the agent currently
trusts an already-authenticated `user_id`), manage secrets via a vault (not `.env`), add rate
limiting and prompt-injection defenses, and audit-log every query with its resolved scope.
**Data masking at the DB layer** (column-level masking / masked views for PII) is the natural next
control, so sensitive fields are protected at the source regardless of who queries. That choice has
an architectural consequence worth flagging: today SQL generation targets a **deterministic contract**
(a fixed scoped schema), which is simple and safe but assumes the accessible surface is known up
front. If masking and access rules become dynamic and policy-driven, it may be worth moving SQL
generation to a **ReAct-style, MCP-agnostic agent** that discovers what it may query at runtime via
tools — trading some determinism for flexibility. The current design deliberately favors the
deterministic contract because it satisfies the present requirement with a far smaller attack surface.

#### Deployment
Each component (DB-MCP server, agent, front ends) is a container; the clean boundaries make them
independently deployable and the per-component CI matrix already mirrors that split. A
**`docker compose`** file ties them together for the local development lifecycle — bring the whole
stack up to run and debug end to end on one machine — while the same images deploy to orchestrated
infra in production. Config is promoted via env (LLM provider/model, DB URL, tracing) with no code
change, releases gate on the lint + per-component test matrix and the eval, and schema changes run
as versioned migrations against the authoritative `schema.sql` contract. One concrete change from
the take-home: swap the local **Ollama** default for **dedicated inference infrastructure** — a
managed LLM endpoint or a GPU-backed self-hosted serving tier — sized and scaled independently per
the queue-buffered model above.
