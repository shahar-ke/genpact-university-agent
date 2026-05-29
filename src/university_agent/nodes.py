"""Graph nodes and routing for the QA agent.

Each node is small and single-purpose; the LLM and the MCP gateway are pulled from the
run config (so tests inject fakes). `user_id` lives in state and is passed to the gateway
on each call — the LLM never sees it.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from pydantic import BaseModel, Field

from university_agent.mcp_gateway import Gateway
from university_agent.state import AgentState

MAX_ATTEMPTS = 3


# ── Structured LLM outputs ──────────────────────────────────────────────────────


class Understanding(BaseModel):
    """Whether the question is answerable from this DB, and a normalized rewrite."""

    in_scope: bool = Field(description="True if answerable from the university database")
    normalized_question: str = Field(description="A precise, self-contained rewrite")


class SqlGeneration(BaseModel):
    """A generated query, or a reason the question can't be answered."""

    answerable: bool = Field(description="False if the data isn't available/accessible")
    sql: str = Field(default="", description="A single read-only SQLite SELECT")
    reason: str = Field(default="", description="Why it can't be answered, if not answerable")


# ── Prompts ─────────────────────────────────────────────────────────────────────

_UNDERSTAND_PROMPT = """You help users query a university database in natural language.
You can ONLY see the relations the current user is allowed to query:

{schema}

User question: {question}

Decide if this is answerable from these relations. Off-topic questions (weather, chit-chat,
anything unrelated to this university data) are NOT in scope. If in scope, rewrite the
question into a precise, self-contained form grounded in the available relations."""

_GENERATE_PROMPT = """You are an expert SQLite analyst. Write ONE read-only SELECT that
answers the question, using ONLY these relations (and their columns):

{schema}

Rules:
- Relations named `my_...` and `me` are ALREADY filtered to the current user. Query them
  directly; NEVER add a WHERE clause on a user's name or id to "find" the current user.
- When the question identifies an entity (which/who teacher, student, course...),
  SELECT its name/title/code, never its numeric id (group by the id if needed, but
  return the readable label).
- SQLite has no PERCENTILE_CONT — use window functions for percentiles.

Example queries:
{examples}

Question: {question}
{feedback}
If the question cannot be answered from the relations above (data not present or not
accessible), set answerable=false and give a short reason. Otherwise return the SQL."""

_SYNTHESIZE_PROMPT = """Answer the user's question from the SQL result. Be concise and
factual; do not invent data. If there are no rows, say there is no matching data.

Question: {question}
Rows ({row_count} total, showing up to 50): {rows}"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _llm(config: RunnableConfig) -> BaseChatModel:
    return config["configurable"]["llm"]


def _gateway(config: RunnableConfig) -> Gateway:
    return config["configurable"]["gateway"]


def render_schema(schema: dict[str, Any]) -> str:
    """Render the MCP schema (relations + columns) into compact prompt text."""
    lines = []
    for relation in schema.get("relations", []):
        columns = ", ".join(column["name"] for column in relation["columns"])
        lines.append(f"- {relation['name']}({columns})")
    return "\n".join(lines) or "(no accessible relations)"


def _retry_feedback(history: list[dict[str, Any]]) -> str:
    """Render all prior failed attempts so the LLM avoids repeating them."""
    if not history:
        return ""
    lines = ["Your previous attempts failed — do not repeat them:"]
    for index, attempt in enumerate(history, start=1):
        lines.append(f"  attempt {index}: {attempt['sql']}\n    -> {attempt['error']}")
    return "\n".join(lines) + "\n"


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def load_schema(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch the user's accessible schema from the MCP server (deterministic, no LLM)."""
    schema = await _gateway(config).get_schema(state["user_id"])
    return {"schema_text": render_schema(schema)}


async def understand_question(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Relevance gate + schema-grounded rewrite of the question."""
    prompt = _UNDERSTAND_PROMPT.format(schema=state["schema_text"], question=state["question"])
    result: Understanding = await _llm(config).with_structured_output(Understanding).ainvoke(prompt)
    return {"in_scope": result.in_scope, "normalized_question": result.normalized_question}


async def generate_sql(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Generate SQL grounded in the schema, or terminate with a reasoned 'cannot answer'."""
    examples = await _gateway(config).get_examples()
    feedback = _retry_feedback(state.get("history", []))
    prompt = _GENERATE_PROMPT.format(
        schema=state["schema_text"],
        examples=examples,
        question=state["normalized_question"],
        feedback=feedback,
    )
    gen: SqlGeneration = await _llm(config).with_structured_output(SqlGeneration).ainvoke(prompt)
    attempts = state.get("attempts", 0) + 1
    if not gen.answerable:
        return {"attempts": attempts, "answer": f"I can't answer that: {gen.reason}"}
    return {"attempts": attempts, "sql": gen.sql}


async def execute_sql(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Run the generated SQL through the MCP server (scope-enforced, read-only)."""
    result = await _gateway(config).execute_sql(state["user_id"], state["sql"])
    update: dict[str, Any] = {"result": result}
    if result.get("status") != "ok":
        error = result.get("reason") or result.get("category") or "unknown error"
        update["history"] = [{"sql": state["sql"], "error": error}]  # reducer appends
    return update


async def synthesize_answer(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Turn result rows into a concise natural-language answer."""
    result = state["result"]
    prompt = _SYNTHESIZE_PROMPT.format(
        question=state["normalized_question"],
        row_count=result["row_count"],
        rows=json.dumps(result["rows"][:50], default=str),
    )
    message = await _llm(config).ainvoke(prompt)
    return {"answer": message.content}


def capabilities_reply(state: AgentState) -> dict[str, Any]:
    """Terminal reply for off-topic questions."""
    return {
        "answer": (
            "I can only answer questions about the university data you have access to — "
            "for example your courses, enrollments, grades, and teachers. "
            "I can't help with topics outside this database."
        )
    }


def give_up(state: AgentState) -> dict[str, Any]:
    """Terminal reply after exhausting SQL retries."""
    history = state.get("history", [])
    last_error = history[-1]["error"] if history else "unknown"
    return {
        "answer": (
            "I couldn't form a valid query for that after several attempts. "
            f"Last issue: {last_error}."
        )
    }


# ── Routing ─────────────────────────────────────────────────────────────────


def route_after_understand(state: AgentState) -> str:
    return "generate_sql" if state.get("in_scope") else "capabilities_reply"


def route_after_generate(state: AgentState) -> str:
    return END if state.get("answer") else "execute_sql"


def route_after_execute(state: AgentState) -> str:
    if state["result"].get("status") == "ok":
        return "synthesize_answer"
    if state.get("attempts", 0) >= MAX_ATTEMPTS:
        return "give_up"
    return "generate_sql"
