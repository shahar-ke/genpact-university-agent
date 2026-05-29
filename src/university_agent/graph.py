"""Assemble the QA agent graph and provide the run entry point.

Topology:
    load_schema -> understand_question
        -> capabilities_reply (END)         # off-topic
        -> generate_sql
             -> END                          # unanswerable (access / not modeled)
             -> execute_sql
                  -> synthesize_answer (END)  # ok
                  -> generate_sql             # rejected/error, retry (capped)
                  -> give_up (END)            # retries exhausted
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from university_agent import mcp_gateway, nodes
from university_agent.llm import make_llm
from university_agent.state import AgentState


def build_graph():
    """Compile the agent graph. The LLM and MCP gateway are supplied per-run via config."""
    graph = StateGraph(AgentState)

    graph.add_node("load_schema", nodes.load_schema)
    graph.add_node("understand_question", nodes.understand_question)
    graph.add_node("capabilities_reply", nodes.capabilities_reply)
    graph.add_node("generate_sql", nodes.generate_sql)
    graph.add_node("execute_sql", nodes.execute_sql)
    graph.add_node("synthesize_answer", nodes.synthesize_answer)
    graph.add_node("give_up", nodes.give_up)

    graph.add_edge(START, "load_schema")
    graph.add_edge("load_schema", "understand_question")
    graph.add_conditional_edges(
        "understand_question",
        nodes.route_after_understand,
        {"generate_sql": "generate_sql", "capabilities_reply": "capabilities_reply"},
    )
    graph.add_conditional_edges(
        "generate_sql",
        nodes.route_after_generate,
        {"execute_sql": "execute_sql", END: END},
    )
    graph.add_conditional_edges(
        "execute_sql",
        nodes.route_after_execute,
        {
            "synthesize_answer": "synthesize_answer",
            "generate_sql": "generate_sql",
            "give_up": "give_up",
        },
    )
    graph.add_edge("capabilities_reply", END)
    graph.add_edge("synthesize_answer", END)
    graph.add_edge("give_up", END)

    return graph.compile()


async def answer_question(
    question: str,
    user_id: str,
    *,
    db_url: str | None = None,
    llm: BaseChatModel | None = None,
) -> str:
    """Run the agent for one question as the given user; returns the answer text.

    Opens one MCP connection for the run (discovery happens here) and injects the LLM +
    gateway into the graph config. The LLM is built from env if not supplied.
    """
    graph = build_graph()
    llm = llm or make_llm()
    async with mcp_gateway.connect(db_url) as gateway:
        final = await graph.ainvoke(
            {"question": question, "user_id": user_id, "attempts": 0},
            config={"configurable": {"llm": llm, "gateway": gateway}},
        )
    return final["answer"]
