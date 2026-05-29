"""Demo CLI: mock-login, then answer questions as the chosen user in a loop.

Pick a role and 'log in' as one of up to three users of that role (mock-login — a direct
directory read, not a scoped query), then ask questions one at a time until you exit.
This is the only module importing both the DB layer and the agent; the agent package never
imports the DB layer.

Loads a .env first, so LLM settings (LLM_PROVIDER / LLM_MODEL) and LangSmith tracing
(LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT) are picked up automatically. When
LangSmith is configured, each answer prints a link to its trace.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv
from langchain_core.tracers.context import tracing_v2_enabled

from university_agent.graph import answer_question
from university_db.directory import list_users_by_role, role_of
from university_db.engine import make_engine
from university_db.roles import Role


def _choose(prompt: str, options: list[str]) -> str:
    """Prompt for a 1-based numeric pick from `options`, re-prompting until one is valid."""
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")
    while True:
        raw = input(f"{prompt} [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Invalid choice, try again.")


def resolve_user(engine, user: str | None, role_name: str | None) -> str:
    """Return the username to act as — explicit --user, else interactive role/user pick."""
    if user:
        return user
    role = Role(role_name) if role_name else Role(_choose("Select a role", [r.value for r in Role]))
    usernames = list_users_by_role(engine, role)
    if not usernames:
        raise SystemExit(f"No users with role {role.value}.")
    return _choose(f"Identify as ({role.value})", usernames)


def _answer(question: str, username: str, role: str | None, db_url: str | None) -> None:
    """Run one question and print the answer (plus a LangSmith trace link when available)."""
    project = os.environ.get("LANGSMITH_PROJECT", "university-agent")
    trace_url = None
    if os.environ.get("LANGSMITH_API_KEY"):
        with tracing_v2_enabled(project_name=project) as cb:
            answer = asyncio.run(answer_question(question, username, db_url=db_url, role=role))
        try:
            trace_url = cb.get_run_url()
        except Exception:
            trace_url = None
    else:
        answer = asyncio.run(answer_question(question, username, db_url=db_url, role=role))

    print("\n" + answer)
    if trace_url:
        print(f"\n  \U0001f50d trace: {trace_url}")


def main() -> None:
    """CLI entry point: load env, mock-login a user, then answer questions in a loop."""
    load_dotenv()
    os.environ.setdefault("LANGSMITH_PROJECT", "university-agent")

    parser = argparse.ArgumentParser(description="University QA agent — demo CLI")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy URL (default: env or sqlite)")
    parser.add_argument("--role", default=None, choices=[r.value for r in Role])
    parser.add_argument("--user", default=None, help="username (skips the login prompts)")
    parser.add_argument("--question", default=None, help="ask one question, then exit")
    args = parser.parse_args()

    engine = make_engine(args.db_url, read_only=True)
    username = resolve_user(engine, args.user, args.role)
    role = role_of(engine, username)
    print(f"\nLogged in as {username} ({role}). Ask one question at a time.")

    if args.question:
        _answer(args.question, username, role, args.db_url)
        return

    while True:
        question = input("\nYour question (or 'exit'): ").strip()
        if question.lower() in {"exit", "quit", ""}:
            print("Bye.")
            return
        _answer(question, username, role, args.db_url)


if __name__ == "__main__":
    main()
