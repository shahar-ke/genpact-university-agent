"""Shared graph state for the QA agent.

TypedDict with total=False so nodes return partial updates that LangGraph merges. Keeping
the SQL and result in state (not hidden in tool calls) is also what makes the LangSmith
trace legible end to end.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class Attempt(TypedDict):
    """One failed SQL attempt: what we tried and why it failed."""

    sql: str
    error: str


class AgentState(TypedDict, total=False):
    # inputs
    question: str
    user_id: str
    # understanding
    schema_text: str
    in_scope: bool
    normalized_question: str
    # query / execution
    sql: str
    attempts: int
    result: dict[str, Any]
    # Accumulated failed attempts (reducer appends), so generate_sql sees the full history
    # and the LLM can avoid repeating a mistake while converging on valid SQL.
    history: Annotated[list[Attempt], operator.add]
    # output
    answer: str
