"""Agent graph: happy path, off-topic, unanswerable, retry-then-succeed, and give-up.

Uses a fake LLM and a fake gateway injected via config, so no Ollama or MCP server is
needed — the topology, routing, and retry cap are exercised deterministically.
"""

import pytest
from langchain_core.messages import AIMessage

from university_agent.graph import build_graph
from university_agent.nodes import SqlGeneration, Understanding

SCHEMA = {
    "relations": [
        {"name": "my_enrollments", "columns": [{"name": "grade", "type": "REAL"}]},
        {"name": "courses", "columns": [{"name": "code", "type": "TEXT"}]},
    ]
}


class _FakeStructured:
    def __init__(self, queue):
        self.queue = queue

    async def ainvoke(self, _prompt):
        return self.queue.pop(0)


class FakeLLM:
    def __init__(self, *, understanding=None, generations=None, answer="Here is your answer."):
        self._understanding = list(understanding or [])
        self._generations = list(generations or [])
        self._answer = answer

    def with_structured_output(self, model):
        if model is Understanding:
            return _FakeStructured(self._understanding)
        if model is SqlGeneration:
            return _FakeStructured(self._generations)
        raise AssertionError(f"unexpected structured model {model}")

    async def ainvoke(self, _prompt):
        return AIMessage(content=self._answer)


# noinspection PyMethodMayBeStatic
class FakeGateway:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.executed = []

    async def get_schema(self, _user_id):
        return SCHEMA

    async def get_examples(self):
        return "-- examples"

    async def execute_sql(self, user_id, sql):
        self.executed.append((user_id, sql))
        return self.responses.pop(0)


async def _run(llm, gateway, question="anything"):
    graph = build_graph()
    return await graph.ainvoke(
        {"question": question, "user_id": "alice", "attempt_num": 0},
        config={"configurable": {"llm": llm, "gateway": gateway}},
    )


@pytest.mark.asyncio
async def test_happy_path():
    llm = FakeLLM(
        understanding=[Understanding(in_scope=True, normalized_question="my grades")],
        generations=[SqlGeneration(answerable=True, sql="SELECT grade FROM my_enrollments")],
        answer="Your average grade is 88.",
    )
    gateway = FakeGateway(responses=[{"status": "ok", "row_count": 1, "rows": [{"grade": 88}]}])
    final = await _run(llm, gateway)
    assert final["answer"] == "Your average grade is 88."
    assert final["sql"] == "SELECT grade FROM my_enrollments"
    assert len(gateway.executed) == 1


@pytest.mark.asyncio
async def test_off_topic_short_circuits():
    llm = FakeLLM(understanding=[Understanding(in_scope=False, normalized_question="")])
    gateway = FakeGateway()
    final = await _run(llm, gateway, question="what's the weather?")
    assert "only answer questions about the university data" in final["answer"]
    assert gateway.executed == []  # never reached SQL


@pytest.mark.asyncio
async def test_compound_question_asks_one_at_a_time():
    llm = FakeLLM(
        understanding=[
            Understanding(in_scope=True, is_compound=True, normalized_question="a and b")
        ]
    )
    gateway = FakeGateway()
    final = await _run(llm, gateway, question="my average grade and which courses am I taking?")
    assert "one question at a time" in final["answer"]
    assert gateway.executed == []  # never reached SQL


@pytest.mark.asyncio
async def test_unanswerable_terminates_at_generation():
    llm = FakeLLM(
        understanding=[Understanding(in_scope=True, normalized_question="other students' grades")],
        generations=[SqlGeneration(answerable=False, reason="you can only see your own grades")],
    )
    gateway = FakeGateway()
    final = await _run(llm, gateway)
    assert "I can't answer that" in final["answer"]
    assert gateway.executed == []


@pytest.mark.asyncio
async def test_retry_then_succeed():
    llm = FakeLLM(
        understanding=[Understanding(in_scope=True, normalized_question="my grades")],
        generations=[
            SqlGeneration(answerable=True, sql="SELECT bad"),
            SqlGeneration(answerable=True, sql="SELECT grade FROM my_enrollments"),
        ],
        answer="You have 3 grades.",
    )
    gateway = FakeGateway(
        responses=[
            {"status": "error", "reason": "no such column: bad"},
            {"status": "ok", "row_count": 3, "rows": [{"grade": 90}]},
        ]
    )
    final = await _run(llm, gateway)
    assert final["answer"] == "You have 3 grades."
    assert len(gateway.executed) == 2  # failed once, then succeeded


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts():
    rejected = {"status": "rejected", "category": "forbidden_relation", "reason": "no access"}
    llm = FakeLLM(
        understanding=[Understanding(in_scope=True, normalized_question="q")],
        generations=[SqlGeneration(answerable=True, sql="SELECT 1") for _ in range(3)],
    )
    gateway = FakeGateway(responses=[rejected, rejected, rejected])
    final = await _run(llm, gateway)
    assert "couldn't form a valid query" in final["answer"]
    assert len(gateway.executed) == 3  # capped at MAX_ATTEMPTS
