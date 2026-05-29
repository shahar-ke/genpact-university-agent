"""Capture / export committed execution traces of the agent flow.

Traces are a *flow* artifact, independent of how the agent is driven (CLI or web): they record
the per-node path question -> reasoning/in_scope -> sql -> result rows -> answer. This lives in
evals/ because it runs the agent over the same fixed `fixture.sql` the harness does
(build_graph() + connect(db_url)), just streaming the node updates instead of scoring.

Two modes:
- default — local capture written under traces/. Works WITHOUT a LangSmith account.
- --from-langsmith — for each local trace recorded with LangSmith on, pull the full run tree
  back from the LangSmith API (root graph run + every node + LLM/tool child runs, with timing
  and token usage) into traces/langsmith/. Needs LANGSMITH_API_KEY; exits cleanly without one.

Run:
    uv run python -m evals.capture_traces
    uv run python -m evals.capture_traces --from-langsmith
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tracers.context import tracing_v2_enabled

from university_agent.graph import build_graph
from university_agent.llm import make_llm
from university_agent.university_db_mcp_gateway import connect
from university_db.directory import list_users_by_role
from university_db.engine import make_engine
from university_db.roles import Role

FIXTURE = Path(__file__).parent / "fixture.sql"
TRACES_DIR = Path(__file__).resolve().parents[1] / "traces"
LANGSMITH_DIR = TRACES_DIR / "langsmith"
_RUN_ID = re.compile(r"/r/([0-9a-f-]+)")  # the run id inside a LangSmith trace URL


@dataclass(frozen=True)
class TraceCase:
    """A representative question to trace, named for its output file."""

    name: str
    role: Role
    question: str


CASES = (
    TraceCase("student_avg_grade", Role.STUDENT, "What is my average grade?"),
    TraceCase("teacher_distinct_students", Role.TEACHER, "How many distinct students do I teach?"),
    TraceCase("admin_top_teacher", Role.ADMIN, "Which teacher has the most enrolled students?"),
)


def _load_fixture(db_path: Path) -> None:
    """Execute the self-contained fixture (schema + inserts) into a fresh SQLite file."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(FIXTURE.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


def _resolve_user(engine, role: Role) -> str:
    """First username for the role (admin resolves to the single 'admin' account)."""
    if role == Role.ADMIN:
        return "admin"
    return list_users_by_role(engine, role, limit=1)[0]


def _merge(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Fold one node's partial update into the running state (append the history reducer)."""
    for key, value in update.items():
        if key == "history" and isinstance(value, list):
            state.setdefault("history", []).extend(value)
        else:
            state[key] = value


async def _stream(question: str, user_id: str, db_url: str, role: str):
    """Stream the graph once; return (final_state, ordered per-node steps)."""
    steps: list[dict[str, Any]] = []
    final: dict[str, Any] = {"question": question}
    async with connect(db_url) as gateway:
        graph = build_graph()
        config = {
            "configurable": {"llm": make_llm(), "gateway": gateway},
            "metadata": {"user_id": user_id, "role": role},
            "tags": [f"user:{user_id}", f"role:{role}"],
        }
        async for chunk in graph.astream(
            {"question": question, "user_id": user_id, "attempt_num": 0}, config=config
        ):
            for node, update in chunk.items():
                steps.append({"node": node, "update": update})
                _merge(final, update)
    return final, steps


def _capture_one(case: TraceCase, user_id: str, db_url: str):
    """Run one case, capturing the flow and a LangSmith trace URL when a key is configured."""
    project = os.environ.get("LANGSMITH_PROJECT", "university-agent")
    trace_url: str | None = None
    if os.environ.get("LANGSMITH_API_KEY"):
        with tracing_v2_enabled(project_name=project) as cb:
            final, steps = asyncio.run(_stream(case.question, user_id, db_url, case.role.value))
        try:
            trace_url = cb.get_run_url()
        except Exception:
            trace_url = None
    else:
        final, steps = asyncio.run(_stream(case.question, user_id, db_url, case.role.value))
    return final, steps, trace_url


def _payload(case: TraceCase, user_id: str, final: dict, steps: list, trace_url) -> dict[str, Any]:
    """Shape one run into the committed JSON record (flow + ordered per-node steps)."""
    return {
        "case": case.name,
        "role": case.role.value,
        "user_id": user_id,
        "question": case.question,
        "flow": {
            "reasoning": final.get("reasoning"),
            "in_scope": final.get("in_scope"),
            "is_compound": final.get("is_compound"),
            "normalized_question": final.get("normalized_question"),
            "sql": final.get("sql"),
            "result": final.get("result"),
            "answer": final.get("answer"),
        },
        "node_steps": steps,
        "langsmith_trace_url": trace_url,
    }


def capture_live() -> None:
    """Build a fixture-backed DB, run each case through the agent, write traces/<name>.json."""
    TRACES_DIR.mkdir(exist_ok=True)
    db_path = Path(tempfile.mkdtemp()) / "trace.db"
    _load_fixture(db_path)
    db_url = f"sqlite:///{db_path}"
    engine = make_engine(db_url, read_only=True)

    for case in CASES:
        user_id = _resolve_user(engine, case.role)
        print(f"Tracing {case.name} as {user_id} ({case.role.value})…")
        final, steps, trace_url = _capture_one(case, user_id, db_url)
        out = TRACES_DIR / f"{case.name}.json"
        out.write_text(
            json.dumps(_payload(case, user_id, final, steps, trace_url), indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  -> {out.relative_to(TRACES_DIR.parent)}")


def export_from_langsmith() -> None:
    """Fetch the full LangSmith run tree for each local trace; write traces/langsmith/<name>.json.

    Resolves the run id from each local trace's `langsmith_trace_url`, so run a local capture
    (with LangSmith on) first. Requires LANGSMITH_API_KEY; exits cleanly without one.
    """
    if not (os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")):
        raise SystemExit(
            "LANGSMITH_API_KEY not set — cannot fetch from the LangSmith API. The local "
            "capture (`uv run python -m evals.capture_traces`, no flag) works without a key."
        )
    sources = sorted(TRACES_DIR.glob("*.json"))
    if not sources:
        raise SystemExit("No traces/*.json to resolve run ids from — run a local capture first.")

    from langsmith import Client  # transitive dep of the agent extra; imported only when needed

    client = Client()
    LANGSMITH_DIR.mkdir(exist_ok=True)
    for src in sources:
        payload = json.loads(src.read_text(encoding="utf-8"))
        match = _RUN_ID.search(payload.get("langsmith_trace_url") or "")
        if not match:
            print(f"  skip {src.name}: no LangSmith run id (was it traced?)")
            continue
        run = client.read_run(match.group(1), load_child_runs=True)
        dest = LANGSMITH_DIR / src.name
        dest.write_text(json.dumps(run.model_dump(mode="json"), indent=2), encoding="utf-8")
        print(
            f"  {src.name}: root + {len(run.child_runs or [])} nodes -> "
            f"{dest.relative_to(TRACES_DIR.parent)}"
        )


def main() -> None:
    """Capture local traces, or (with --from-langsmith) export the live LangSmith trees."""
    parser = argparse.ArgumentParser(description="Capture or export agent execution traces")
    parser.add_argument(
        "--from-langsmith",
        action="store_true",
        help="export full run trees from the LangSmith API (needs LANGSMITH_API_KEY)",
    )
    args = parser.parse_args()
    load_dotenv()
    if args.from_langsmith:
        export_from_langsmith()
    else:
        capture_live()


if __name__ == "__main__":
    main()
