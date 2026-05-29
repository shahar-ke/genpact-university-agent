"""Run the evaluation across models x cases over the fixed fixture; write report.md.

Each model that is available (Ollama model pulled, or API key present) runs; others are
skipped and noted. Per case the agent runs against a fresh DB built from fixture.sql and is
scored by category:
  good     -> the agent's result contains the canonical (god-mode) values
  bad      -> the agent refuses / returns no successful data result
  compound -> the agent routes to the one-at-a-time reply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from evals.cases import CASES, TOPICS, EvalCase, category_of
from university_agent.graph import build_graph
from university_agent.llm import make_llm
from university_agent.university_db_mcp_gateway import connect
from university_db.directory import list_users_by_role
from university_db.engine import make_engine
from university_db.roles import Role

FIXTURE = Path(__file__).parent / "fixture.sql"
REPORT = Path(__file__).parent / "report.md"

# (label, provider, model id). Commercial ids are editable; keys come from env/.env.
MODELS = [
    ("gemma2:9b", "ollama", "gemma2:9b"),
    ("llama3.1:8b", "ollama", "llama3.1:8b"),
    ("claude-sonnet", "anthropic", "claude-sonnet-4-6"),
    ("gpt-5.4-mini", "openai", "gpt-5.4-mini"),  # 'gpt-5.5-mini' doesn't exist; this is newest mini
]


def _model_available(provider: str, model: str) -> bool:
    if provider == "ollama":
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
            return model in out.stdout
        except Exception:
            return False
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    return False


def _load_fixture(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(FIXTURE.read_text(encoding="utf-8"))
    con.commit()
    con.close()


def _resolve_username(engine, role: str) -> str:
    if role == "admin":
        return "admin"
    return list_users_by_role(engine, Role(role), limit=1)[0]


def _norm(value: Any) -> Any:
    return round(value, 2) if isinstance(value, float) else value


def _flatten(rows: list[Any]) -> set[Any]:
    values: set[Any] = set()
    for row in rows:
        cells = row.values() if isinstance(row, dict) else row
        for cell in cells if isinstance(cells, list | tuple | type({}.values())) else [cells]:
            if cell is not None:
                values.add(_norm(cell))
    return values


def _ground_truth(db_path: Path, case: EvalCase, username: str) -> set[Any]:
    if category_of(case.topic) != "good":
        return set()
    con = sqlite3.connect(db_path)
    try:
        params = {"username": username} if ":username" in case.ground_truth_sql else {}
        rows = con.execute(case.ground_truth_sql, params).fetchall()
    finally:
        con.close()
    return _flatten(rows)


def _score(case: EvalCase, state: dict[str, Any], expected: set[Any]) -> bool:
    category = category_of(case.topic)
    answer = (state.get("answer") or "").lower()
    if category == "compound":
        return "one question at a time" in answer
    if category == "bad":
        result = state.get("result")
        return not (result and result.get("status") == "ok")
    agent_values = _flatten((state.get("result") or {}).get("rows", []))
    return bool(expected) and all(value in agent_values for value in expected)


async def _run_model(cases: list[EvalCase], engine, db_path: Path, db_url: str) -> list[dict]:
    out = []
    async with connect(db_url) as gateway:  # one MCP connection for this model's cases
        graph = build_graph()
        llm = make_llm()
        for case in cases:
            username = _resolve_username(engine, case.role)
            expected = _ground_truth(db_path, case, username)
            start = time.time()
            try:
                state = await graph.ainvoke(
                    {"question": case.question, "user_id": username, "attempt_num": 0},
                    config={"configurable": {"llm": llm, "gateway": gateway}},
                )
                ok = _score(case, state, expected)
            except Exception as exc:  # a model/agent failure is a failed case, not a crash
                state, ok = {"answer": f"ERROR: {exc}"}, False
            out.append(
                {
                    "case": case,
                    "ok": ok,
                    "state": state,
                    "elapsed": time.time() - start,
                    "expected": expected,
                }
            )
    return out


def _render_report(results: dict[str, list[dict]], skipped: list[str]) -> str:
    topics = list(TOPICS)
    lines = [
        "# Evaluation report",
        "",
        f"Dataset: fixed `evals/fixture.sql`. Cases: {len(CASES)}. Temperature 0.",
        "",
        "## Topics",
    ]
    lines += [f"- **{topic}** — {desc}" for topic, desc in TOPICS.items()]
    lines.append(
        "\nScoring: good topics (aggregation/filtering/joins/multi_step) pass when the answer "
        "contains the canonical god-mode value; access_control/relevance pass when the agent "
        "**declines** (scope is enforced server-side, so no model can leak regardless — this "
        "measures graceful refusal); compound passes when routed to the one-at-a-time reply."
    )
    if skipped:
        lines.append(f"\nSkipped (unavailable): {', '.join(skipped)}.")

    header = "| Model | Total | " + " | ".join(topics) + " | Latency (s) |"
    sep = "|---|---|" + "|".join(["---"] * len(topics)) + "|---|"
    lines += ["", "## Scores", "", header, sep]
    for label, rows in results.items():
        cells = []
        for topic in topics:
            tr = [r for r in rows if r["case"].topic == topic]
            cells.append(f"{sum(r['ok'] for r in tr)}/{len(tr)}" if tr else "-")
        total = f"{sum(r['ok'] for r in rows)}/{len(rows)}"
        avg = sum(r["elapsed"] for r in rows) / len(rows) if rows else 0
        lines.append(f"| {label} | {total} | " + " | ".join(cells) + f" | {avg:.1f} |")

    for label, rows in results.items():
        lines += [
            "",
            f"## {label} — details",
            "",
            "| Case | Topic | Pass | Agent SQL | Answer |",
            "|---|---|---|---|---|",
        ]
        for r in rows:
            state, case = r["state"], r["case"]
            sql = (state.get("sql") or "").replace("\n", " ").replace("|", "/")[:70]
            ans = (state.get("answer") or "").replace("\n", " ").replace("|", "/")[:70]
            mark = "✅" if r["ok"] else "❌"
            lines.append(f"| {case.id} | {case.topic} | {mark} | `{sql}` | {ans} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agent evaluation")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--only", default=None, help="comma-separated model labels to run")
    parser.add_argument("--cases", default=None, help="comma-separated case ids to run")
    parser.add_argument("--out", default=str(REPORT), help="report output path")
    args = parser.parse_args()
    load_dotenv(override=True)  # .env is authoritative for the harness (beats empty env vars)

    cases = CASES
    if args.cases:
        wanted = {cid.strip() for cid in args.cases.split(",")}
        cases = [c for c in cases if c.id in wanted]
    if args.limit:
        cases = cases[: args.limit]
    only = {label.strip() for label in args.only.split(",")} if args.only else None
    models = [m for m in MODELS if only is None or m[0] in only]

    tmp = Path(tempfile.mkdtemp()) / "eval.db"
    _load_fixture(tmp)
    db_url = f"sqlite:///{tmp}"
    engine = make_engine(db_url, read_only=True)

    results: dict[str, list[dict]] = {}
    skipped: list[str] = []
    for label, provider, model in models:
        if not _model_available(provider, model):
            skipped.append(label)
            continue
        os.environ["LLM_PROVIDER"] = provider
        os.environ["LLM_MODEL"] = model
        print(f"Running {label} ...")
        results[label] = asyncio.run(_run_model(cases, engine, tmp, db_url))

    out = Path(args.out)
    out.write_text(_render_report(results, skipped), encoding="utf-8")
    print(f"Wrote {out}  (ran: {list(results)}; skipped: {skipped})")


if __name__ == "__main__":
    main()
