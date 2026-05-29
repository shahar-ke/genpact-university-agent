# university_web

A **Streamlit** demo + validation UI over the same agent — a second front end alongside the
[CLI](../university_cli/README.md). Like the CLI it's a **composition root**: the one web-side
module tree allowed to import both the [DB layer](../university_db/README.md) and the
[agent](../university_agent/README.md) (the agent package still never imports the DB layer).

## What it does

Two deliberately separate pages over one working SQLite file (switch via the sidebar nav):

- **Data view (god-mode / validation)** — a direct, **read-only** read of every table in an
  Ag-Grid with per-column sort + filter. It **bypasses the agent and per-user scoping** on
  purpose: it exists so you can check the agent's answers against ground truth.
- **Query tool (scoped agent path)** — the real agent: pick **role → user → question** and see
  the answer, the generated SQL, the result rows, the scope decision (reasoning / in_scope /
  is_compound), and a LangSmith trace link when configured. Identity is enforced **server-side**
  by the MCP server, so a student sees only their own data, an admin everything.

A shared sidebar builds the working DB from either the **fixed eval fixture** (`evals/fixture.sql`)
or a **fresh random seed** (with adjustable row counts), so both pages run against the same data.

```bash
uv sync --extra web                                   # streamlit + streamlit-aggrid + pandas
uv run university-web                                  # launch (sugar for `streamlit run .../app.py`)
uv run university-web-traces                           # write committed per-node JSON traces under traces/
uv run university-web-traces --from-langsmith          # export the live LangSmith run trees (needs a key)
```

## Design / key files

| File | Role |
|---|---|
| `app.py` | the Streamlit app: shared sidebar (data control) + the two pages (Data view, Query tool) |
| `agent_runner.py` | runs the scoped agent for one question, **streaming** the per-node flow (question → reasoning → sql → rows → answer) and capturing a trace URL; wraps the async graph in `asyncio.run` for sync Streamlit |
| `data.py` | working-DB control (`build_db` from fixture or seed) + read-only god-mode table reads (imports only `university_db`) |
| `launcher.py` | the `university-web` console script — hands off to Streamlit's CLI, forwarding extra args |
| `traces.py` | the `university-web-traces` script — default mode runs one representative question per role and writes each full flow as committed JSON under `traces/` (LangSmith-free); `--from-langsmith` instead pulls the full run trees back from the LangSmith API into `traces/langsmith/` |

## Behavior without a LangSmith key

Nothing crashes. `agent_runner` only enters `tracing_v2_enabled` when `LANGSMITH_API_KEY` is
set; otherwise the agent runs untraced and no trace link is shown — the CLI and web Query tool
both work the same way. The local trace capture still writes its JSON (`langsmith_trace_url:
null`). Only `university-web-traces --from-langsmith` needs a key (it reads the LangSmith API)
and exits with a clear message if it is missing.

## Main libraries

| Library | Why |
|---|---|
| **streamlit** | the multi-page web UI (sidebar nav, widgets, layout) |
| **streamlit-aggrid** | the data grids with per-column sort + floating filters (Data view + result rows) |
| **pandas** | dataframes feeding the grids |
| **python-dotenv** | load `.env` (LLM provider/model + LangSmith) at startup |
| **langchain-core** | `tracing_v2_enabled` to capture a per-run LangSmith trace URL |

It pulls in the full `all` stack transitively (the agent path spawns the MCP server). Installed
via the `web` extra (`uv sync --extra web`).
