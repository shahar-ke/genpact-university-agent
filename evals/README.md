# evals

The evaluation harness: run the [agent](../src/university_agent/README.md) over a **fixed
dataset** across multiple models, score by topic, and write a comparison report.

## What it does

- **Fixed dataset** — `fixture.sql` is a committed dump of a small deterministic DB (built by
  `build_fixture.py` from a tiny `SeedConfig`). Each case runs against a fresh DB loaded from it,
  so results are constant and inspectable. Re-run `build_fixture.py` only to change the data.
- **50 cases across 7 topics** (`cases.py`) — each case has a `topic` (capability under test) and
  a `role` (resolved to a concrete fixture user). The scoring category derives from the topic:

  | Category | Topics | Passes when |
  |---|---|---|
  | **good** | aggregation, filtering, joins, multi_step | the answer contains the canonical god-mode value (from `ground_truth_sql`) |
  | **bad** | access_control, relevance | the agent **declines** (scope is enforced server-side regardless — this measures *graceful refusal*) |
  | **compound** | compound | the agent routes to the one-question-at-a-time reply |

- **Multi-model comparison** (`run_eval.py`) — runs each available model (Ollama model pulled,
  or API key present; others skipped and noted), scores per topic + total with average latency,
  and writes `report.md`. Flags: `--only`, `--cases`, `--limit`, `--out`.

```bash
ollama pull llama3.1:8b                  # + ANTHROPIC_API_KEY / OPENAI_API_KEY in .env
uv run python -m evals.run_eval          # writes evals/report.md
```

- **Execution traces** (`capture_traces.py`) — runs one representative question per role through
  the agent over the fixture and writes each full per-node flow (question → reasoning → sql →
  rows → answer) as committed JSON under `traces/`. A flow artifact, independent of CLI vs. web;
  `--from-langsmith` instead pulls the full run trees back from the LangSmith API.

```bash
uv run python -m evals.capture_traces                  # local capture (works without a key)
uv run python -m evals.capture_traces --from-langsmith # export full LangSmith run trees (needs a key)
```

## Key files

| File | Role |
|---|---|
| `cases.py` | the 50 `EvalCase`s, `TOPICS`, and topic→category mapping |
| `fixture.sql` | committed deterministic dataset (the constant the eval runs against) |
| `build_fixture.py` | regenerate `fixture.sql` from a small `SeedConfig` |
| `run_eval.py` | run models × cases, score, render `report.md` |
| `capture_traces.py` | write committed per-node execution traces under `traces/` (`--from-langsmith` exports the live run trees) |

## Main libraries

| Library | Why |
|---|---|
| **langchain-anthropic** / **langchain-openai** | the commercial providers compared against the local Ollama models |
| **python-dotenv** | `.env` is authoritative for the harness (API keys, provider config) |

These (plus the full `all` stack) come from the `eval` extra: `uv sync --extra eval`.
