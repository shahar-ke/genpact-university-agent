"""User-directory lookups for the demo's mock-login.

This is a pre-auth convenience (listing accounts to 'log in' as), NOT part of the scoped
query path — so it reads the users table directly rather than going through the agent/MCP.
"""

from __future__ import annotations

from sqlalchemy import Engine, select

from university_db.engine import session_scope
from university_db.models import User
from university_db.roles import Role


def list_users_by_role(engine: Engine, role: Role, limit: int = 3) -> list[str]:
    """Return up to `limit` usernames for the given role, ordered for stable demo output."""
    with session_scope(engine) as session:
        rows = (
            session.execute(
                select(User.username).where(User.role == role).order_by(User.username).limit(limit)
            )
            .scalars()
            .all()
        )
    return list(rows)
