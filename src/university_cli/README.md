# university_cli

The demo CLI and **composition root** — the only module that imports both the
[DB layer](../university_db/README.md) and the [agent](../university_agent/README.md) (the agent
package itself never imports the DB layer). Exposed as the `university-agent-cli` console script.

## What it does

1. **Mock-login** — pick a role, then "log in" as one of up to three users of that role. This is
   a direct directory read (`university_db.directory`), *not* a scoped query — it's pre-auth
   convenience for the demo.
2. **Question loop** — ask one question at a time as the chosen user; `--question` runs a single
   question and exits, `--user` / `--role` skip the prompts.
3. **Tracing** — loads `.env` first so LLM settings and LangSmith config are picked up
   automatically; when `LANGSMITH_API_KEY` is set, each answer prints a link to its trace.

```bash
# ask one question and exit (no prompts)
uv run university-agent-cli --user admin --question "which teacher has the most enrolled students?"

# or run with no flags for the interactive role/user prompts
uv run university-agent-cli
```

The `role` is attached to the run for trace metadata/tags only — access control is enforced
server-side from `user_id`, not from anything the CLI passes.

## Main libraries

| Library | Why |
|---|---|
| **python-dotenv** | load `.env` (LLM provider/model + LangSmith settings) before the run |
| **langchain-core** | `tracing_v2_enabled` to capture a per-question LangSmith trace URL |

It pulls in the `db` + `agent` extras transitively. Installed via the `cli` extra
(`uv sync --extra cli`).
