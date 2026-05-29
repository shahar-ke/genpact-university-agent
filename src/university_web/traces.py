"""Capture / export execution traces of the system flow.

Two modes:

- default — run a few representative questions (one per role) through the real agent
  (build_graph() + connect(db_url), exactly as the eval harness and web app do) and write each
  run's full per-node flow (question -> reasoning/in_scope -> sql -> result rows -> answer) as
  JSON under traces/. This is a *local* capture and works WITHOUT a LangSmith account.

- --from-langsmith — for each local trace that was recorded with LangSmith on, pull the full
  run tree back from the LangSmith API (root graph run + every node + LLM/tool child runs, with
  timing and token usage) and write it under traces/langsmith/. Requires LANGSMITH_API_KEY;
  exits with a clear message if it is missing.

Run:
    uv run university-web-traces                  # local capture
    uv run university-web-traces --from-langsmith # export the live LangSmith trees
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from university_db.directory import list_users_by_role
from university_db.engine import make_engine
from university_db.roles import Role
from university_web import data
from university_web.agent_runner import run_question

TRACES_DIR = Path(__file__).resolve().parents[2] / "traces"
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


def _resolve_user(engine, role: Role) -> str:
    """First username for the role (admin resolves to the single 'admin' account)."""
    return list_users_by_role(engine, role, limit=1)[0]


def _trace_payload(case: TraceCase, user_id: str, result) -> dict[str, Any]:
    """Shape one run into the committed JSON record (flow + ordered per-node steps)."""
    final = result.final
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
        "node_steps": result.steps,
        "langsmith_trace_url": result.trace_url,
    }


def capture_live() -> None:
    """Build a fixture-backed DB, run each case through the agent, write traces/<name>.json."""
    TRACES_DIR.mkdir(exist_ok=True)
    db_path = Path(tempfile.mkdtemp()) / "trace.db"
    data.build_db(db_path, source="fixture")
    db_url = f"sqlite:///{db_path}"
    engine = make_engine(db_url, read_only=True)

    for case in CASES:
        user_id = _resolve_user(engine, case.role)
        print(f"Tracing {case.name} as {user_id} ({case.role.value})…")
        result = run_question(case.question, user_id, db_url, role=case.role.value)
        out = TRACES_DIR / f"{case.name}.json"
        out.write_text(
            json.dumps(_trace_payload(case, user_id, result), indent=2, default=str),
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
            "capture (`uv run university-web-traces`, no flag) works without a key."
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
