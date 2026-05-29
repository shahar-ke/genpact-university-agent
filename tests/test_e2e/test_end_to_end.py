"""End-to-end: real graph -> real MCP server subprocess -> real SQLite.

Only the LLM is stubbed (so no Ollama needed); everything else is real, including MCP
discovery and the scope-enforced execution path. Requires the full stack (--extra all).
"""

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from university_agent.graph import answer_question
from university_agent.nodes import SqlGeneration, Understanding
from university_db.engine import make_engine, session_scope
from university_db.models import User
from university_db.schema import apply_schema
from university_db.seed import SeedConfig, generate


# noinspection PyMethodMayBeStatic
class _StubLLM:
    """Canned structured outputs + a fixed synthesized answer."""

    def with_structured_output(self, model):
        # noinspection PyMethodMayBeStatic
        class _Structured:
            async def ainvoke(self, _prompt):
                if model is Understanding:
                    return Understanding(in_scope=True, normalized_question="count my enrollments")
                return SqlGeneration(
                    answerable=True, sql="SELECT COUNT(*) AS n FROM my_enrollments"
                )

        return _Structured()

    async def ainvoke(self, _prompt):
        return AIMessage(content="You are enrolled in several courses.")


# noinspection PyTypeChecker
@pytest.mark.asyncio
async def test_agent_runs_against_real_mcp_server(tmp_path):
    url = f"sqlite:///{tmp_path / 'e2e.db'}"
    engine = make_engine(url, read_only=False)
    apply_schema(engine)
    with session_scope(engine) as session:
        generate(session, SeedConfig(teachers=2, students=5, courses=4, semesters=3, retakes=1))
        student = session.execute(
            select(User.username).where(User.role == "student").limit(1)
        ).scalar_one()

    answer = await answer_question(
        "how many courses am I enrolled in?", student, db_url=url, llm=_StubLLM()
    )
    assert answer == "You are enrolled in several courses."
