# university_agent

The **LangGraph agent**: typed state, a small graph of single-purpose nodes, a
provider-agnostic LLM factory, and the MCP gateway. It has **no dependency on
[university_db](../university_db/README.md)** — by design, it never touches the database or SQL
libraries directly. It talks to the [MCP server](../university_db_mcp/README.md) as a client,
*discovering* its tools/resources at connect time rather than re-declaring them.

## Graph topology

```
load_schema → understand_question
    → capabilities_reply (END)          # off-topic
    → single_question_reply (END)       # compound (multi-part) question
    → generate_sql
         → END                          # unanswerable (data not present / not accessible)
         → execute_sql
              → synthesize_answer (END)  # ok
              → generate_sql             # rejected/error → retry (capped at MAX_ATTEMPTS)
              → give_up (END)            # retries exhausted
```

The agent keeps the SQL and result *in state* (not hidden inside tool calls), which is also
what makes the end-to-end LangSmith trace legible. `user_id` lives in state and is passed to the
gateway on each call — the LLM never sees it.

## Design / key files

| File | Role |
|---|---|
| `graph.py` | assembles + compiles the graph; `answer_question` runs one question, opens the MCP connection, injects the LLM + gateway via config, and tags the run with user/role |
| `state.py` | `AgentState` (`TypedDict`, `total=False`); a reducer appends failed attempts to `history` so retries don't repeat mistakes |
| `nodes.py` | the nodes + routing; structured LLM outputs (`Understanding`, `SqlGeneration`), prompts, and the relevance/compound/self-correction logic |
| `llm.py` | provider-agnostic `make_llm()` from `LLM_PROVIDER` / `LLM_MODEL` / `LLM_TEMPERATURE` |
| `university_db_mcp_gateway.py` | spawns + connects to the MCP server, discovers tools/resources; nodes depend only on the small `Gateway` protocol (a fake satisfies it in tests) |

**Self-correction.** On a `rejected`/`error` result, `execute_sql` records the failed SQL + reason
in `history`; `generate_sql` feeds the full history back to the LLM so it converges on valid SQL,
capped at `MAX_ATTEMPTS` (then `give_up`). **Guards** short-circuit before any SQL: off-topic
questions get a capabilities reply, multi-part questions are asked one-at-a-time.

## Main libraries

| Library | Why |
|---|---|
| **langgraph** | the agent graph — nodes, conditional edges, retry loop, typed state |
| **langchain** / **langchain-core** | `init_chat_model` (provider-agnostic LLM) + structured output |
| **langchain-ollama** | local open-source models (default `gemma2:9b`) |
| **langchain-mcp-adapters** | discover and call the MCP server's tools/resources |
| **mcp** | MCP client plumbing (stdio transport) |

Commercial providers are opt-in: `uv pip install langchain-anthropic` (or `langchain-openai`),
then set `LLM_PROVIDER` / `LLM_MODEL`. Installed via the `agent` extra (note: **no SQLAlchemy** —
that's the point). `uv sync --extra agent`.
