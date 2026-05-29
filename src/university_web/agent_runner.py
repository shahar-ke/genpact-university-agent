"""Run the scoped agent and capture its full per-node flow + an optional trace link.

Mirrors evals/run_eval._run_model: build_graph() + connect(db_url), then ainvoke through
the graph (the MCP subprocess inherits db_url as DATABASE_URL and enforces scope server-
side). We additionally stream the per-node updates so the UI and the committed trace
artifact can show question -> reasoning/in_scope -> sql -> result rows -> answer.

The agent is async and Streamlit is sync, so callers go through `run_question`, which wraps
one asyncio.run per query (same pattern as the demo CLI).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tracers.context import tracing_v2_enabled

from university_agent.graph import build_graph
from university_agent.llm import make_llm
from university_agent.university_db_mcp_gateway import connect

# State keys that make up the visible flow, in the order they are produced.
FLOW_KEYS: tuple[str, ...] = (
    "question",
    "reasoning",
    "in_scope",
    "is_compound",
    "normalized_question",
    "sql",
    "result",
    "answer",
)


@dataclass
class RunResult:
    """One agent run: final merged state, the ordered per-node updates, and a trace URL."""

    final: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    trace_url: str | None = None


def _merge(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Fold one node's partial update into the running state (append the history reducer)."""
    for key, value in update.items():
        if key == "history" and isinstance(value, list):
            state.setdefault("history", []).extend(value)
        else:
            state[key] = value


async def _astream(
    question: str, user_id: str, db_url: str | None, role: str | None, llm: BaseChatModel | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Stream the graph once, returning (final_state, per-node steps)."""
    steps: list[dict[str, Any]] = []
    final: dict[str, Any] = {"question": question}
    metadata: dict[str, str] = {"user_id": user_id}
    tags = [f"user:{user_id}"]
    if role:
        metadata["role"] = role
        tags.append(f"role:{role}")
    async with connect(db_url) as gateway:
        graph = build_graph()
        config = {
            "configurable": {"llm": llm or make_llm(), "gateway": gateway},
            "metadata": metadata,
            "tags": tags,
        }
        async for chunk in graph.astream(
            {"question": question, "user_id": user_id, "attempt_num": 0}, config=config
        ):
            for node, update in chunk.items():
                steps.append({"node": node, "update": update})
                _merge(final, update)
    return final, steps


def run_question(
    question: str,
    user_id: str,
    db_url: str | None = None,
    *,
    role: str | None = None,
    llm: BaseChatModel | None = None,
) -> RunResult:
    """Run one question as `user_id`; capture the flow and a LangSmith link when configured."""
    project = os.environ.get("LANGSMITH_PROJECT", "university-agent")
    trace_url: str | None = None
    if os.environ.get("LANGSMITH_API_KEY"):
        with tracing_v2_enabled(project_name=project) as cb:
            final, steps = asyncio.run(_astream(question, user_id, db_url, role, llm))
        try:
            trace_url = cb.get_run_url()
        except Exception:
            trace_url = None
    else:
        final, steps = asyncio.run(_astream(question, user_id, db_url, role, llm))
    return RunResult(final=final, steps=steps, trace_url=trace_url)
