# Evaluation — leaderboard

A committed summary of the agent evaluation. The per-model, per-case detail lives in the generated
`report.<model>.md` files (git-ignored — regenerate with `python -m evals.run_eval`; see
[evals/README.md](README.md)). This file is the stable, reviewable headline.

## What is measured

Dataset: the fixed `evals/fixture.sql` (same bytes on every machine). **50 cases** across 7 topics,
each run at temperature 0. The cases are defined in [`cases.py`](cases.py).

| Topic | Cases | What it checks |
|---|---|---|
| **aggregation** | 12 | Counts, averages, min/max over the user's permitted data |
| **filtering** | 8 | Selecting/counting rows by condition (grade thresholds, term, year) |
| **joins** | 8 | Combining scoped data with the public catalog (course code/title, teacher name) |
| **multi_step** | 6 | CTEs / window functions / ranking (percentiles, top-N, highest-average) |
| **access_control** | 9 | Illegal cross-user / cross-role / column requests — must be refused |
| **relevance** | 4 | Off-topic questions — must be declined |
| **compound** | 3 | Multi-part questions — must be routed to "ask one at a time" |

**Scoring.** The four "good" topics (aggregation/filtering/joins/multi_step) pass when the answer
contains the canonical god-mode value computed directly from the fixture. `access_control` and
`relevance` pass when the agent **declines** — note this measures *graceful refusal only*: scope is
enforced server-side, so no model can actually leak data regardless of its score here. `compound`
passes when the agent routes to the one-at-a-time reply.

## Leaderboard

All models that were available at run time, scored over the same 50 cases (best total first).

| Model | Total | aggregation | filtering | joins | multi_step | access_control | relevance | compound | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet (`claude-sonnet-4-6`) | **45/50** | 12/12 | 8/8 | 8/8 | 6/6 | 5/9 | 4/4 | 2/3 | 7.3 |
| gpt-5.4-mini | **41/50** | 11/12 | 8/8 | 6/8 | 6/6 | 3/9 | 4/4 | 3/3 | 2.9 |
| gemma2:9b (local) | **33/50** | 10/12 | 6/8 | 2/8 | 3/6 | 5/9 | 4/4 | 3/3 | 11.2 |

## Reading the results

- **The architecture, not the model, is what guarantees safety.** Across every model, **no run
  leaked data** on the access-control cases — the server-side scope holds regardless. A lower
  `access_control` score reflects a model answering "there is no matching data" instead of an
  explicit decline, not a leak.
- **Model capability shows up on the hard SQL.** The frontier model is near-perfect on the good
  topics; the local `gemma2:9b` is solid on aggregation/filtering but weak on `joins` and
  `multi_step` (multi-table reasoning, CTEs, window functions) — a model-quality gap, not a
  pipeline bug.
- **The pipeline is provider-agnostic**, so swapping the model (local → frontier) is a config
  change, and this leaderboard is how that trade-off (quality vs. latency vs. cost/locality) is
  compared on identical inputs.
