"""Demo CLI: mock-login, then run the QA agent as the chosen user.

Pick a role and 'log in' as one of up to three users of that role (mock-login — a direct
directory read, not a scoped query), ask a question, and the agent answers as that user.
This is the only module importing both the DB layer and the agent; the agent package never
imports the DB layer.

Loads a .env first, so LLM settings (LLM_PROVIDER / LLM_MODEL) and LangSmith tracing
(LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT) are picked up automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from university_agent.graph import answer_question
from university_db.directory import list_users_by_role
from university_db.engine import make_engine
from university_db.roles import Role


def _choose(prompt: str, options: list[str]) -> str:
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


def main() -> None:
    load_dotenv()
    os.environ.setdefault("LANGSMITH_PROJECT", "university-agent")

    parser = argparse.ArgumentParser(description="University QA agent — demo CLI")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy URL (default: env or sqlite)")
    parser.add_argument("--role", default=None, choices=[r.value for r in Role])
    parser.add_argument("--user", default=None, help="username (skips the login prompts)")
    parser.add_argument("--question", default=None, help="question (skips the prompt)")
    args = parser.parse_args()

    engine = make_engine(args.db_url, read_only=True)
    username = resolve_user(engine, args.user, args.role)
    question = args.question or input("Your question: ").strip()

    answer = asyncio.run(answer_question(question, username, db_url=args.db_url))
    print("\n" + answer)


if __name__ == "__main__":
    main()
